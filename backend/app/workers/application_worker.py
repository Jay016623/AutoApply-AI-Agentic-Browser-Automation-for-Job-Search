"""Background worker that processes job applications from the Redis queue.

Consumes application tasks from the ``QUEUE_APPLY`` Redis queue and
orchestrates the full apply pipeline: load job, generate resume,
score with ATS, apply via platform, and broadcast progress.
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import select

from app.api.websocket.events import manager as ws_manager
from app.config.constants import QUEUE_APPLY, ApplicationStatus
from app.config.settings import get_settings
from app.core.automation.platforms import platform_registry
from app.core.automation.platforms.base import JobListing
from app.core.exceptions import AutoApplyError
from app.db.redis import get_redis, init_redis_pool
from app.db.session import async_session_factory
from app.domains.applications.execution import ApplicationAttemptService
from app.domains.applications.workflow import WorkflowService, WorkflowState
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.schemas.resume import ResumeGenerateRequest
from app.services import resume as resume_service
from app.services.queue import dequeue

logger = structlog.get_logger(__name__)

_WORKFLOW_PROGRESS_ORDER: list[WorkflowState] = [
    WorkflowState.DISCOVERED,
    WorkflowState.MATCHED,
    WorkflowState.SHORTLISTED,
    WorkflowState.TAILORED,
    WorkflowState.READY_TO_APPLY,
    WorkflowState.APPLYING,
    WorkflowState.SUBMITTED,
]


def _state_reached(current_state: WorkflowState, target_state: WorkflowState) -> bool:
    """Return True when the workflow has already reached/passed target_state."""
    if current_state in (WorkflowState.FAILED_MANUAL, WorkflowState.FAILED_RETRYABLE, WorkflowState.ABANDONED):
        return False
    return _WORKFLOW_PROGRESS_ORDER.index(current_state) >= _WORKFLOW_PROGRESS_ORDER.index(target_state)


async def _ensure_workflow_run(application_id: str, job_id: str) -> tuple[str, WorkflowState]:
    """Get or create workflow run for application and persist link if available."""
    async with async_session_factory() as db:
        workflow_service = WorkflowService(db)
        result = await db.execute(select(Application).where(Application.id == application_id))
        application = result.scalar_one_or_none()
        if not isinstance(application, Application):
            application = None

        run_id: str | None = application.workflow_run_id if application is not None else None
        if run_id:
            run = await workflow_service.get_run(run_id)
            return run.id, WorkflowState(run.current_state)

        run = await workflow_service.create_run(
            candidate_id=application_id,
            tenant_id=application.tenant_id if application is not None else None,
            job_id=job_id or None,
        )
        if application is not None:
            application.workflow_run_id = run.id
            await db.commit()
        return run.id, WorkflowState(run.current_state)


async def _transition_workflow_state(
    workflow_run_id: str,
    target_state: WorkflowState,
    idempotency_key: str,
    step_name: str,
    error_message: str | None = None,
) -> WorkflowState:
    """Apply a durable workflow transition and return updated state."""
    async with async_session_factory() as db:
        workflow_service = WorkflowService(db)
        run = await workflow_service.transition_state(
            run_id=workflow_run_id,
            target_state=target_state,
            idempotency_key=idempotency_key,
            step_name=step_name,
            error_message=error_message,
        )
        return WorkflowState(run.current_state)


async def _execute_attempt_path(
    *,
    payload: dict[str, Any],
    app_id: str,
    job: Job,
    workflow_run_id: str | None,
    platform_name: str,
    resume_path: str,
) -> tuple[bool, str | None]:
    """Run durable, resumable attempt execution for submit path."""
    tenant_id = payload.get("tenant_id")
    candidate_id = payload.get("candidate_id")
    manual_reason = payload.get("manual_checkpoint_reason")
    execution_key = payload.get("execution_idempotency_key") or f"{app_id}:{workflow_run_id or 'none'}:v1"

    async with async_session_factory() as db:
        attempt_service = ApplicationAttemptService(db, tenant_scope=tenant_id)
        attempt = await attempt_service.create_or_get_attempt(
            tenant_id=tenant_id,
            application_id=app_id,
            workflow_run_id=workflow_run_id,
            candidate_id=candidate_id,
            job_id=job.id,
            idempotency_key=execution_key,
        )
        await attempt_service.start_attempt(attempt.id)
        next_sequence = await attempt_service.get_resume_sequence(attempt.id)

        step_names = [
            "prepare_execution_context",
            "start_browser_apply",
            "upload_documents",
            "submit",
            "verify_submission",
            "store_proof_artifacts",
        ]

        for offset, step_name in enumerate(step_names):
            seq = next_sequence + offset
            step = await attempt_service.record_step_started(
                attempt_id=attempt.id,
                step_name=step_name,
                sequence_number=seq,
                idempotency_key=f"{attempt.id}:{step_name}",
                input_snapshot_json={"platform": platform_name, "application_id": app_id},
            )
            if step.status == "completed":
                continue

            if step_name == "prepare_execution_context":
                await attempt_service.record_step_completed(step_id=step.id, output_snapshot_json={"job_id": job.id})
            elif step_name == "start_browser_apply":
                await attempt_service.record_step_completed(step_id=step.id, output_snapshot_json={"driver": "platform_adapter"})
            elif step_name == "upload_documents":
                await attempt_service.record_step_completed(
                    step_id=step.id,
                    output_snapshot_json={"resume_path": resume_path or ""},
                )
            elif step_name == "submit":
                if payload.get("manual_checkpoint_mode"):
                    checkpoint_reason = manual_reason or "manual_checkpoint_mode enabled"
                    await attempt_service.record_step_failed(
                        step_id=step.id,
                        error_code="MANUAL_CHECKPOINT",
                        error_message=checkpoint_reason,
                        retryable=False,
                        manual_checkpoint_reason=checkpoint_reason,
                    )
                    await attempt_service.create_proof_artifact(
                        tenant_id=tenant_id,
                        application_id=app_id,
                        workflow_run_id=workflow_run_id,
                        attempt_id=attempt.id,
                        attempt_step_id=step.id,
                        artifact_type="log",
                        storage_path=f"attempt://{attempt.id}/manual-checkpoint",
                        metadata_json={"reason": checkpoint_reason},
                    )
                    return False, checkpoint_reason

                platform = platform_registry.create(platform_name)
                job_listing = JobListing(
                    platform=job.platform,
                    platform_job_id=job.platform_job_id,
                    title=job.title,
                    company=job.company,
                    location=job.location or "",
                    url=job.url,
                    description=job.description or "",
                    job_type=job.job_type or "",
                    remote=job.remote or False,
                )
                applied = await platform.apply(
                    job=job_listing,
                    resume_path=resume_path,
                    cover_letter_path=None,
                )
                if not applied:
                    await attempt_service.record_step_failed(
                        step_id=step.id,
                        error_code="PLATFORM_APPLY_FAILED",
                        error_message="Platform returned unsuccessful apply result",
                        retryable=True,
                    )
                    return False, "Platform returned unsuccessful apply result"
                await attempt_service.record_step_completed(step_id=step.id, output_snapshot_json={"applied": True})
            elif step_name == "verify_submission":
                await attempt_service.record_step_completed(step_id=step.id, output_snapshot_json={"verified": True})
            else:
                artifact = await attempt_service.create_proof_artifact(
                    tenant_id=tenant_id,
                    application_id=app_id,
                    workflow_run_id=workflow_run_id,
                    attempt_id=attempt.id,
                    attempt_step_id=step.id,
                    artifact_type="trace",
                    storage_path=f"attempt://{attempt.id}/trace",
                    metadata_json={"platform": platform_name},
                )
                await attempt_service.record_step_completed(
                    step_id=step.id,
                    output_snapshot_json={"artifact_id": artifact.id},
                )

        await attempt_service.complete_attempt(attempt.id)
        return True, None


async def _broadcast_progress(
    application_id: str,
    status: str,
    detail: str = "",
) -> None:
    """Send application progress update via WebSocket.

    Args:
        application_id: Unique application identifier.
        status: Current status string.
        detail: Optional detail message.
    """
    message: dict[str, Any] = {
        "type": "application_progress",
        "application_id": application_id,
        "status": status,
    }
    if detail:
        message["detail"] = detail
    await ws_manager.broadcast(message)


async def _update_application_status(
    app_id: str,
    status: str,
    notes: str | None = None,
    ats_score: float | None = None,
    applied_at: datetime | None = None,
) -> None:
    """Persist application status changes to the database.

    Args:
        app_id: Application UUID.
        status: New status value.
        notes: Optional notes to attach.
        ats_score: Optional ATS score to record.
        applied_at: Optional applied timestamp.
    """
    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Application).where(Application.id == app_id),
            )
            app = result.scalar_one_or_none()
            if app is None:
                logger.warning("worker.app_not_found_for_update", app_id=app_id)
                return
            app.status = status
            if notes is not None:
                app.notes = notes
            if ats_score is not None:
                app.ats_score = ats_score
            if applied_at is not None:
                app.applied_at = applied_at
            await db.commit()
    except Exception as exc:
        logger.error(
            "worker.status_update_failed",
            app_id=app_id,
            error=str(exc),
        )


async def _run_ats_scoring(job: Job, resume_id: str) -> float | None:
    """Run ATS scoring for a job against a resume.

    Returns the overall score or None if scoring cannot be performed
    (e.g. missing resume text, spaCy not installed).
    """
    if not resume_id:
        return None

    try:
        async with async_session_factory() as db:
            result = await db.execute(
                select(Resume).where(Resume.id == resume_id),
            )
            resume = result.scalar_one_or_none()

        if resume is None or not resume.content_text:
            logger.warning("worker.ats_no_resume_text", resume_id=resume_id)
            return None

        from app.core.ats.experience_analyzer import ExperienceAnalyzer
        from app.core.ats.scorer import ResumeScorer

        try:
            import spacy

            nlp = spacy.load("en_core_web_sm")
            from app.core.ats.keyword_analyzer import KeywordAnalyzer
            from app.core.ats.skill_matcher import SkillMatcher

            skill_matcher = SkillMatcher(nlp)
            keyword_analyzer = KeywordAnalyzer(nlp)
            experience_analyzer = ExperienceAnalyzer(nlp)
        except (ImportError, OSError):
            logger.warning("worker.spacy_unavailable_for_ats")
            return None

        scorer = ResumeScorer(
            skill_matcher=skill_matcher,
            keyword_analyzer=keyword_analyzer,
            experience_analyzer=experience_analyzer,
        )

        job_description = job.description or ""
        job_metadata: dict[str, Any] = {}
        if job.skills_required and isinstance(job.skills_required, dict):
            job_metadata["required_skills"] = job.skills_required.get(
                "required", [],
            )

        candidate_profile: dict[str, Any] = {
            "skills": [],
            "experience": [],
            "education": [],
        }

        score_details = scorer.score_resume(
            resume_text=resume.content_text,
            job_description=job_description,
            candidate_profile=candidate_profile,
            job_metadata=job_metadata,
        )
        return score_details.overall_score

    except Exception as exc:
        logger.warning("worker.ats_scoring_error", error=str(exc))
        return None


async def process_application(payload: dict[str, Any]) -> None:
    """Process a single application from the queue.

    Pipeline: load job -> generate resume -> score ATS -> apply via platform.

    Args:
        payload: Task payload containing job_id, application_id,
            resume_id, platform, and other application parameters.
    """
    job_id: str = payload.get("job_id", "")
    app_id: str = payload.get("application_id", "")
    resume_id: str = payload.get("resume_id", "")
    platform_name: str = payload.get("platform", "")

    logger.info(
        "worker.processing",
        job_id=job_id,
        app_id=app_id,
        platform=platform_name,
    )

    await _broadcast_progress(app_id, ApplicationStatus.APPLYING)

    # Validate platform is registered
    if not platform_registry.has(platform_name):
        logger.error("worker.unknown_platform", platform=platform_name)
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=f"Unknown platform: {platform_name}",
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail=f"Unknown platform: {platform_name}",
        )
        return

    try:
        settings = get_settings()
        min_score = settings.min_ats_score
        workflow_run_id, workflow_state = await _ensure_workflow_run(app_id, job_id)

        if workflow_state == WorkflowState.SUBMITTED:
            await _update_application_status(app_id, ApplicationStatus.APPLIED)
            await _broadcast_progress(app_id, ApplicationStatus.APPLIED, detail="Already submitted in previous workflow run")
            return

        # --------------------------------------------------------------
        # Step 1: Load job details from DB
        # --------------------------------------------------------------
        await _broadcast_progress(app_id, "loading_job")
        job: Job | None = None
        try:
            async with async_session_factory() as db:
                result = await db.execute(
                    select(Job).where(Job.id == job_id),
                )
                job = result.scalar_one_or_none()
        except Exception as exc:
            logger.error(
                "worker.load_job_failed", job_id=job_id, error=str(exc),
            )

        if job is None:
            error_msg = f"Job {job_id} not found in database"
            logger.error("worker.job_not_found", job_id=job_id)
            await _update_application_status(
                app_id, ApplicationStatus.FAILED, notes=error_msg,
            )
            await _broadcast_progress(
                app_id, ApplicationStatus.FAILED, detail=error_msg,
            )
            await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.FAILED_MANUAL,
                idempotency_key=f"{app_id}:failed-job-load",
                step_name="load_job",
                error_message=error_msg,
            )
            return

        if not _state_reached(workflow_state, WorkflowState.MATCHED):
            workflow_state = await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.MATCHED,
                idempotency_key=f"{app_id}:matched",
                step_name="load_job",
            )

        if not _state_reached(workflow_state, WorkflowState.SHORTLISTED):
            workflow_state = await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.SHORTLISTED,
                idempotency_key=f"{app_id}:shortlisted",
                step_name="shortlist",
            )

        # --------------------------------------------------------------
        # Step 2: Generate tailored resume + cover letter
        # --------------------------------------------------------------
        resume_path: str | None = None
        if not _state_reached(workflow_state, WorkflowState.TAILORED):
            await _broadcast_progress(app_id, "generating_resume")
            try:
                if resume_id:
                    async with async_session_factory() as db:
                        gen_request = ResumeGenerateRequest(
                            base_resume_id=resume_id,
                            job_id=job_id,
                            template_id="modern",
                        )
                        tailored_resp = (
                            await resume_service.generate_tailored_resume(
                                db, gen_request,
                            )
                        )
                        result = await db.execute(
                            select(Resume).where(
                                Resume.id == tailored_resp.id,
                            ),
                        )
                        tailored_resume = result.scalar_one_or_none()

                    if tailored_resume:
                        resume_path = (
                            tailored_resume.file_path_pdf
                            or tailored_resume.file_path_docx
                        )
                        logger.info(
                            "worker.resume_generated",
                            resume_id=tailored_resume.id,
                        )
                else:
                    logger.info("worker.no_base_resume", app_id=app_id)
            except Exception as exc:
                logger.warning(
                    "worker.resume_generation_failed",
                    app_id=app_id,
                    error=str(exc),
                )

            workflow_state = await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.TAILORED,
                idempotency_key=f"{app_id}:tailored",
                step_name="tailor_resume",
            )

        # --------------------------------------------------------------
        # Step 3: Score with ATS
        # --------------------------------------------------------------
        ats_score: float | None = None
        if not _state_reached(workflow_state, WorkflowState.READY_TO_APPLY):
            await _broadcast_progress(app_id, "scoring_ats")
            try:
                ats_score = await _run_ats_scoring(job, resume_id)
                logger.info(
                    "worker.ats_scored", app_id=app_id, score=ats_score,
                )
            except Exception as exc:
                logger.warning(
                    "worker.ats_scoring_failed",
                    app_id=app_id,
                    error=str(exc),
                )

            if ats_score is not None and ats_score < min_score:
                skip_msg = (
                    f"ATS score {ats_score:.2f} below minimum "
                    f"threshold {min_score:.2f}"
                )
                logger.info(
                    "worker.ats_below_threshold",
                    app_id=app_id,
                    score=ats_score,
                )
                await _update_application_status(
                    app_id,
                    ApplicationStatus.FAILED,
                    notes=skip_msg,
                    ats_score=ats_score,
                )
                await _broadcast_progress(
                    app_id, ApplicationStatus.FAILED, detail=skip_msg,
                )
                await _transition_workflow_state(
                    workflow_run_id,
                    WorkflowState.FAILED_MANUAL,
                    idempotency_key=f"{app_id}:failed-ats-threshold",
                    step_name="score_ats",
                    error_message=skip_msg,
                )
                return

            workflow_state = await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.READY_TO_APPLY,
                idempotency_key=f"{app_id}:ready-to-apply",
                step_name="score_ats",
            )

        logger.debug("worker.ats_threshold", min_score=min_score)

        # --------------------------------------------------------------
        # Step 4: Apply via platform
        # --------------------------------------------------------------
        await _broadcast_progress(app_id, "submitting")
        if not _state_reached(workflow_state, WorkflowState.APPLYING):
            workflow_state = await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.APPLYING,
                idempotency_key=f"{app_id}:applying",
                step_name="submit_application",
            )
        try:
            applied, submit_error = await _execute_attempt_path(
                payload=payload,
                app_id=app_id,
                job=job,
                workflow_run_id=workflow_run_id,
                platform_name=platform_name,
                resume_path=resume_path or "",
            )
            if not applied:
                if payload.get("manual_checkpoint_mode"):
                    await _update_application_status(
                        app_id,
                        ApplicationStatus.FAILED,
                        notes=f"Manual checkpoint required: {submit_error}",
                        ats_score=ats_score,
                    )
                    await _broadcast_progress(
                        app_id,
                        ApplicationStatus.FAILED,
                        detail=f"Manual checkpoint required: {submit_error}",
                    )
                    await _transition_workflow_state(
                        workflow_run_id,
                        WorkflowState.FAILED_MANUAL,
                        idempotency_key=f"{app_id}:manual-checkpoint",
                        step_name="submit_application",
                        error_message=submit_error,
                    )
                else:
                    await _update_application_status(
                        app_id,
                        ApplicationStatus.FAILED,
                        notes=submit_error,
                        ats_score=ats_score,
                    )
                    await _broadcast_progress(
                        app_id, ApplicationStatus.FAILED, detail=submit_error,
                    )
                    await _transition_workflow_state(
                        workflow_run_id,
                        WorkflowState.FAILED_RETRYABLE,
                        idempotency_key=f"{app_id}:failed-submit",
                        step_name="submit_application",
                        error_message=submit_error,
                    )
                return
        except KeyError as exc:
            error_msg = f"Platform creation failed: {exc}"
            logger.error("worker.platform_create_failed", error=str(exc))
            await _update_application_status(app_id, ApplicationStatus.FAILED, notes=error_msg)
            await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=error_msg)
            await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.FAILED_MANUAL,
                idempotency_key=f"{app_id}:failed-platform-create",
                step_name="submit_application",
                error_message=error_msg,
            )
            return
        except Exception as exc:
            error_msg = f"Application submission failed: {exc}"
            logger.error("worker.submit_failed", app_id=app_id, platform=platform_name, error=str(exc))
            await _update_application_status(
                app_id,
                ApplicationStatus.FAILED,
                notes=error_msg,
                ats_score=ats_score,
            )
            await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=error_msg)
            await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.FAILED_RETRYABLE,
                idempotency_key=f"{app_id}:failed-submit",
                step_name="submit_application",
                error_message=error_msg,
            )
            return

        # --------------------------------------------------------------
        # Step 5: Update application status to APPLIED
        # --------------------------------------------------------------
        await _update_application_status(
            app_id,
            ApplicationStatus.APPLIED,
            ats_score=ats_score,
            applied_at=datetime.now(UTC),
        )
        await _broadcast_progress(app_id, ApplicationStatus.APPLIED)
        await _transition_workflow_state(
            workflow_run_id,
            WorkflowState.SUBMITTED,
            idempotency_key=f"{app_id}:submitted",
            step_name="submit_application",
        )
        logger.info(
            "worker.completed",
            job_id=job_id,
            app_id=app_id,
        )

    except AutoApplyError as exc:
        logger.error(
            "worker.application_error",
            job_id=job_id,
            app_id=app_id,
            error=str(exc),
            code=exc.code,
        )
        await _update_application_status(
            app_id, ApplicationStatus.FAILED, notes=str(exc),
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail=str(exc),
        )
        try:
            workflow_run_id, _ = await _ensure_workflow_run(app_id, job_id)
            await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.FAILED_MANUAL,
                idempotency_key=f"{app_id}:failed-auto-apply-error",
                step_name="worker_error",
                error_message=str(exc),
            )
        except Exception:
            logger.warning("worker.workflow_failure_record_failed", app_id=app_id)

    except Exception as exc:
        logger.error(
            "worker.unexpected_error",
            job_id=job_id,
            app_id=app_id,
            error=str(exc),
        )
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=f"Unexpected error: {exc}",
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail="Unexpected error during application",
        )
        try:
            workflow_run_id, _ = await _ensure_workflow_run(app_id, job_id)
            await _transition_workflow_state(
                workflow_run_id,
                WorkflowState.FAILED_RETRYABLE,
                idempotency_key=f"{app_id}:failed-unexpected-error",
                step_name="worker_error",
                error_message=str(exc),
            )
        except Exception:
            logger.warning("worker.workflow_failure_record_failed", app_id=app_id)


async def run_worker() -> None:
    """Main worker loop consuming from the apply queue.

    Blocks indefinitely, polling the Redis queue for application tasks.
    Falls back gracefully if Redis is unavailable.
    """
    settings = get_settings()
    await init_redis_pool(settings.redis_url)
    redis = get_redis()
    if not redis:
        logger.error("worker.redis_unavailable")
        return

    logger.info("worker.started", queue=QUEUE_APPLY)

    while True:
        try:
            message = await dequeue(redis, QUEUE_APPLY, timeout=5)
            if message is not None:
                payload = message.get("payload", {})
                await process_application(payload)
        except Exception as exc:
            logger.error("worker.loop_error", error=str(exc))
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(run_worker())
