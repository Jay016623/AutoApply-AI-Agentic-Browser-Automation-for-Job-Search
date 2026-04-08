"""Background worker that processes job applications from the Redis queue.

Consumes application tasks from the ``QUEUE_APPLY`` Redis queue and
orchestrates the full apply pipeline: load job, generate resume,
score with ATS, apply via platform, and broadcast progress.
"""

import asyncio
from pathlib import Path
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
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.schemas.resume import ResumeGenerateRequest
from app.services import execution_visibility as visibility_service
from app.services import resume as resume_service
from app.services.queue import dequeue

logger = structlog.get_logger(__name__)


def _derive_checkpoint_from_error(error_message: str) -> tuple[str, str, str] | None:
    """Map actionable blocker evidence to manual checkpoint details."""
    lowered = error_message.lower()
    if "unsupported" in lowered and "form" in lowered:
        return (
            "unsupported_form",
            "UNSUPPORTED_FORM",
            error_message,
        )
    if "confirmation" in lowered or "confirm" in lowered:
        return (
            "ambiguous_confirmation",
            "AMBIGUOUS_CONFIRMATION",
            error_message,
        )
    return None


async def _record_artifact_if_persisted(
    *,
    tenant_id: str,
    application_id: str,
    attempt_id: str,
    step_id: str | None,
    artifact_type: str,
    storage_uri: str | None,
    content_type: str | None = None,
    metadata_json: dict | None = None,
) -> None:
    """Persist proof artifact only when path/uri is real and persisted."""
    if not storage_uri:
        return
    if storage_uri.startswith(("http://", "https://")):
        persisted = True
    else:
        persisted = Path(storage_uri).exists()
    if not persisted:
        return
    async with async_session_factory() as db:
        await visibility_service.record_proof_artifact(
            db,
            tenant_id=tenant_id,
            application_id=application_id,
            attempt_id=attempt_id,
            step_id=step_id,
            artifact_type=artifact_type,
            storage_uri=storage_uri,
            content_type=content_type,
            metadata_json=metadata_json,
        )


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
    payload_tenant_id: str | None = payload.get("tenant_id")
    execution_task_id: str | None = payload.get("execution_task_id")
    trigger_reason: str | None = payload.get("enqueue_reason")

    logger.info(
        "worker.processing",
        job_id=job_id,
        app_id=app_id,
        platform=platform_name,
        tenant_id=payload_tenant_id,
    )

    attempt_id: str | None = None
    current_step_id: str | None = None
    step_order = 0
    app_tenant_id: str | None = payload_tenant_id
    candidate_id: str | None = None

    async def _start_step(step_name: str, metadata: dict | None = None) -> str | None:
        nonlocal current_step_id, step_order
        if attempt_id is None or app_tenant_id is None:
            return None
        step_order += 1
        async with async_session_factory() as db:
            step = await visibility_service.start_step(
                db,
                tenant_id=app_tenant_id,
                attempt_id=attempt_id,
                application_id=app_id,
                step_name=step_name,
                step_order=step_order,
                metadata_json=metadata,
            )
        current_step_id = step.id
        return current_step_id

    async def _complete_step(metadata: dict | None = None) -> None:
        if current_step_id is None:
            return
        async with async_session_factory() as db:
            await visibility_service.complete_step(
                db,
                step_id=current_step_id,
                metadata_json=metadata,
            )

    async def _fail_step(error_code: str, error_message: str, metadata: dict | None = None) -> None:
        if current_step_id is None:
            return
        async with async_session_factory() as db:
            await visibility_service.fail_step(
                db,
                step_id=current_step_id,
                error_code=error_code,
                error_message=error_message,
                metadata_json=metadata,
            )

    async def _finalize_attempt(status: str, error_code: str | None = None, error_message: str | None = None) -> None:
        if attempt_id is None:
            return
        async with async_session_factory() as db:
            await visibility_service.finalize_attempt(
                db,
                attempt_id=attempt_id,
                status=status,
                error_code=error_code,
                error_message=error_message,
            )

    async def _create_checkpoint_from_error(error_message: str) -> bool:
        if attempt_id is None or app_tenant_id is None:
            return False
        derived = _derive_checkpoint_from_error(error_message)
        if derived is None:
            return False
        checkpoint_type, reason_code, reason_message = derived
        async with async_session_factory() as db:
            await visibility_service.create_manual_checkpoint(
                db,
                tenant_id=app_tenant_id,
                application_id=app_id,
                attempt_id=attempt_id,
                step_id=current_step_id,
                checkpoint_type=checkpoint_type,
                reason_code=reason_code,
                reason_message=reason_message,
                blocker_confidence="high",
            )
        await _finalize_attempt(
            visibility_service.ATTEMPT_STATUS_INTERRUPTED,
            error_code=reason_code,
            error_message=reason_message,
        )
        return True

    if payload_tenant_id:
        async with async_session_factory() as db:
            attempt = await visibility_service.start_attempt(
                db,
                tenant_id=payload_tenant_id,
                application_id=app_id,
                candidate_id=None,
                trigger_reason=trigger_reason,
                execution_task_id=execution_task_id,
                worker_trace_id=execution_task_id or app_id,
            )
            attempt_id = attempt.id

    await _broadcast_progress(app_id, ApplicationStatus.APPLYING)
    settings = get_settings()

    # Load application context first so attempt can be persisted with tenant linkage.
    await _broadcast_progress(app_id, "loading_job")
    await _start_step("load_context")
    job: Job | None = None
    try:
        async with async_session_factory() as db:
            app_result = await db.execute(
                select(Application).where(Application.id == app_id),
            )
            app_row = app_result.scalar_one_or_none()
            if app_row is not None:
                app_tenant_id = app_row.tenant_id or app_tenant_id
                execution_task_id = execution_task_id or app_row.execution_task_id
                candidate_id = None
                if app_row.resume_id:
                    resume_result = await db.execute(
                        select(Resume).where(Resume.id == app_row.resume_id),
                    )
                    resume_row = resume_result.scalar_one_or_none()
                    if resume_row is not None:
                        candidate_id = resume_row.candidate_id

            result = await db.execute(
                select(Job).where(Job.id == job_id),
            )
            job = result.scalar_one_or_none()
    except Exception as exc:
        await _fail_step("LOAD_CONTEXT_ERROR", str(exc))
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=f"Context loading failed: {exc}",
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail="Failed to load application context",
        )
        return

    if app_tenant_id and attempt_id is None:
        async with async_session_factory() as db:
            attempt = await visibility_service.start_attempt(
                db,
                tenant_id=app_tenant_id,
                application_id=app_id,
                candidate_id=candidate_id,
                trigger_reason=trigger_reason,
                execution_task_id=execution_task_id,
                worker_trace_id=execution_task_id or app_id,
            )
            attempt_id = attempt.id
    else:
        logger.warning("worker.visibility_skipped_missing_tenant", app_id=app_id)

    if settings.feature_flags.tenant_enforcement and not payload_tenant_id:
        detail = "Execution payload missing tenant_id in strict mode."
        await _fail_step("MISSING_TENANT", detail)
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=detail,
        )
        await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=detail)
        await _finalize_attempt(
            visibility_service.ATTEMPT_STATUS_FAILED,
            error_code="MISSING_TENANT",
            error_message=detail,
        )
        return

    if not platform_registry.has(platform_name):
        detail = f"Unknown platform: {platform_name}"
        logger.error("worker.unknown_platform", platform=platform_name)
        await _fail_step("UNKNOWN_PLATFORM", detail)
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=detail,
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail=detail,
        )
        await _finalize_attempt(
            visibility_service.ATTEMPT_STATUS_FAILED,
            error_code="UNKNOWN_PLATFORM",
            error_message=detail,
        )
        return

    if job is None:
        error_msg = f"Job {job_id} not found in database"
        logger.error("worker.job_not_found", job_id=job_id)
        await _fail_step("JOB_NOT_FOUND", error_msg)
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=error_msg,
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail=error_msg,
        )
        await _finalize_attempt(
            visibility_service.ATTEMPT_STATUS_FAILED,
            error_code="JOB_NOT_FOUND",
            error_message=error_msg,
        )
        return

    if settings.feature_flags.tenant_enforcement:
        if not app_tenant_id or not job.tenant_id or app_tenant_id != job.tenant_id:
            detail = "Tenant mismatch between payload/application/job in strict mode."
            await _fail_step("TENANT_MISMATCH", detail)
            await _update_application_status(
                app_id,
                ApplicationStatus.FAILED,
                notes=detail,
            )
            await _broadcast_progress(
                app_id,
                ApplicationStatus.FAILED,
                detail=detail,
            )
            await _finalize_attempt(
                visibility_service.ATTEMPT_STATUS_FAILED,
                error_code="TENANT_MISMATCH",
                error_message=detail,
            )
            return
    await _complete_step({"job_id": job_id, "platform": platform_name})

    try:
        min_score = settings.min_ats_score
        resume_path: str | None = None

        # Verification phase
        await _start_step("verification", {"tenant_id": app_tenant_id, "platform": platform_name})
        await _complete_step()

        # Resume preparation (entered only when resume exists)
        if resume_id:
            await _broadcast_progress(app_id, "generating_resume")
            await _start_step("resume_preparation", {"resume_id": resume_id})
            try:
                async with async_session_factory() as db:
                    gen_request = ResumeGenerateRequest(
                        base_resume_id=resume_id,
                        job_id=job_id,
                        template_id="modern",
                    )
                    tailored_resp = await resume_service.generate_tailored_resume(
                        db,
                        gen_request,
                        tenant_id=app_tenant_id,
                    )
                    result = await db.execute(
                        select(Resume).where(
                            Resume.id == tailored_resp.id,
                        ),
                    )
                    tailored_resume = result.scalar_one_or_none()

                if tailored_resume:
                    resume_path = tailored_resume.file_path_pdf or tailored_resume.file_path_docx
                    await _record_artifact_if_persisted(
                        tenant_id=app_tenant_id or "",
                        application_id=app_id,
                        attempt_id=attempt_id or "",
                        step_id=current_step_id,
                        artifact_type="generated_resume",
                        storage_uri=resume_path,
                        content_type=(
                            "application/pdf"
                            if resume_path and resume_path.endswith(".pdf")
                            else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        ),
                        metadata_json={"resume_id": tailored_resume.id},
                    )
                await _complete_step({"resume_path": resume_path})
            except Exception as exc:
                logger.warning(
                    "worker.resume_generation_failed",
                    app_id=app_id,
                    error=str(exc),
                )
                await _fail_step("RESUME_PREPARATION_FAILED", str(exc))

        # ATS scoring remains informational, no explicit step persisted.
        await _broadcast_progress(app_id, "scoring_ats")
        ats_score: float | None = None
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
            await _update_application_status(
                app_id,
                ApplicationStatus.FAILED,
                notes=skip_msg,
                ats_score=ats_score,
            )
            await _broadcast_progress(
                app_id, ApplicationStatus.FAILED, detail=skip_msg,
            )
            await _finalize_attempt(
                visibility_service.ATTEMPT_STATUS_FAILED,
                error_code="ATS_BELOW_THRESHOLD",
                error_message=skip_msg,
            )
            return

        # Platform submission
        await _broadcast_progress(app_id, "submitting")
        await _start_step("platform_submission", {"platform": platform_name})
        try:
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
                resume_path=resume_path or "",
                cover_letter_path=None,
            )
            if not applied:
                raise AutoApplyError(
                    "Platform returned unsuccessful apply result",
                    code="PLATFORM_APPLY_FAILED",
                )
            await _complete_step({"submitted": True})
        except KeyError as exc:
            error_msg = f"Platform creation failed: {exc}"
            await _fail_step("PLATFORM_CREATE_FAILED", error_msg)
            await _update_application_status(app_id, ApplicationStatus.FAILED, notes=error_msg)
            await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=error_msg)
            await _finalize_attempt(
                visibility_service.ATTEMPT_STATUS_FAILED,
                error_code="PLATFORM_CREATE_FAILED",
                error_message=error_msg,
            )
            return
        except Exception as exc:
            error_msg = f"Application submission failed: {exc}"
            await _fail_step("PLATFORM_SUBMISSION_FAILED", error_msg)
            checkpoint_created = await _create_checkpoint_from_error(error_msg)
            if checkpoint_created:
                await _update_application_status(
                    app_id,
                    ApplicationStatus.FAILED,
                    notes=error_msg,
                    ats_score=ats_score,
                )
                await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=error_msg)
                return
            await _update_application_status(
                app_id,
                ApplicationStatus.FAILED,
                notes=error_msg,
                ats_score=ats_score,
            )
            await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=error_msg)
            await _finalize_attempt(
                visibility_service.ATTEMPT_STATUS_FAILED,
                error_code="PLATFORM_SUBMISSION_FAILED",
                error_message=error_msg,
            )
            return

        # Submission verification (entered because platform returned success)
        await _start_step("submission_verification")
        await _complete_step({"result": "platform_apply_true"})

        await _update_application_status(
            app_id,
            ApplicationStatus.APPLIED,
            ats_score=ats_score,
            applied_at=datetime.now(UTC),
        )
        await _broadcast_progress(app_id, ApplicationStatus.APPLIED)
        await _finalize_attempt(visibility_service.ATTEMPT_STATUS_SUCCEEDED)
        logger.info(
            "worker.completed",
            job_id=job_id,
            app_id=app_id,
            attempt_id=attempt_id,
        )

    except AutoApplyError as exc:
        await _fail_step(exc.code or "AUTOAPPLY_ERROR", str(exc))
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=str(exc),
        )
        await _broadcast_progress(app_id, ApplicationStatus.FAILED, detail=str(exc))
        await _finalize_attempt(
            visibility_service.ATTEMPT_STATUS_FAILED,
            error_code=exc.code or "AUTOAPPLY_ERROR",
            error_message=str(exc),
        )

    except Exception as exc:
        detail = f"Unexpected error: {exc}"
        await _fail_step("UNEXPECTED_ERROR", detail)
        checkpoint_created = await _create_checkpoint_from_error(detail)
        await _update_application_status(
            app_id,
            ApplicationStatus.FAILED,
            notes=detail,
        )
        await _broadcast_progress(
            app_id,
            ApplicationStatus.FAILED,
            detail="Unexpected error during application",
        )
        if not checkpoint_created:
            await _finalize_attempt(
                visibility_service.ATTEMPT_STATUS_FAILED,
                error_code="UNEXPECTED_ERROR",
                error_message=detail,
            )


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
