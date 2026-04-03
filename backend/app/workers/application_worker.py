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
from app.models.application import Application
from app.models.resume import Resume
from app.services import resume as resume_service
from app.services.queue import dequeue
from app.workers.orchestration.artifacts import ArtifactOrchestrator
from app.workers.orchestration.state_transition import StateTransitionOrchestrator
from app.workers.orchestration.submission import SubmissionOrchestrator
from app.workers.orchestration.verification import VerificationOrchestrator

logger = structlog.get_logger(__name__)


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

    transitions = StateTransitionOrchestrator(
        update_status=_update_application_status,
        broadcast_progress=_broadcast_progress,
    )
    verifier = VerificationOrchestrator(
        session_factory=async_session_factory,
        platform_registry=platform_registry,
    )
    artifacts = ArtifactOrchestrator(
        session_factory=async_session_factory,
        resume_service=resume_service,
    )
    submission = SubmissionOrchestrator(platform_registry=platform_registry)

    await transitions.progress(app_id, ApplicationStatus.APPLYING)

    # Validate platform is registered
    platform_check = verifier.verify_platform(platform_name)
    if not platform_check.ok:
        logger.error("worker.unknown_platform", platform=platform_name)
        await transitions.fail(
            app_id,
            detail=platform_check.error,
            notes=platform_check.error,
        )
        return

    try:
        settings = get_settings()
        min_score = settings.min_ats_score

        # --------------------------------------------------------------
        # Step 1: Load job details from DB
        # --------------------------------------------------------------
        await transitions.progress(app_id, "loading_job")
        job = await verifier.load_job(job_id)

        if job is None:
            error_msg = f"Job {job_id} not found in database"
            logger.error("worker.job_not_found", job_id=job_id)
            await transitions.fail(
                app_id,
                detail=error_msg,
                notes=error_msg,
            )
            return

        # --------------------------------------------------------------
        # Step 2: Generate tailored resume + cover letter
        # --------------------------------------------------------------
        await transitions.progress(app_id, "generating_resume")
        resume_path: str | None = None
        artifact_bundle = await artifacts.generate_for_application(
            job_id=job_id,
            resume_id=resume_id,
        )
        resume_path = artifact_bundle.resume_path
        if resume_path:
            logger.info("worker.resume_generated", app_id=app_id)
        elif not resume_id:
            logger.info("worker.no_base_resume", app_id=app_id)

        # --------------------------------------------------------------
        # Step 3: Score with ATS
        # --------------------------------------------------------------
        await transitions.progress(app_id, "scoring_ats")
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

        ats_check = verifier.verify_ats_threshold(ats_score, min_score)
        if not ats_check.ok:
            logger.info("worker.ats_below_threshold", app_id=app_id, score=ats_score)
            await transitions.fail(
                app_id,
                detail=ats_check.error,
                notes=ats_check.error,
                ats_score=ats_score,
            )
            return

        logger.debug("worker.ats_threshold", min_score=min_score)

        # --------------------------------------------------------------
        # Step 4: Apply via platform
        # --------------------------------------------------------------
        await transitions.progress(app_id, "submitting")
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
        submit_result = await submission.submit(
            platform_name=platform_name,
            job=job_listing,
            resume_path=resume_path or "",
            cover_letter_path=None,
        )
        if not submit_result.success:
            await transitions.fail(
                app_id,
                detail=submit_result.error,
                notes=submit_result.error,
                ats_score=ats_score,
            )
            return

        # --------------------------------------------------------------
        # Step 5: Update application status to APPLIED
        # --------------------------------------------------------------
        await transitions.applied(
            app_id,
            ats_score=ats_score,
            applied_at=datetime.now(UTC),
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
        await transitions.fail(
            app_id,
            detail=str(exc),
            notes=str(exc),
        )

    except Exception as exc:
        logger.error(
            "worker.unexpected_error",
            job_id=job_id,
            app_id=app_id,
            error=str(exc),
        )
        await transitions.fail(
            app_id,
            detail="Unexpected error during application",
            notes=f"Unexpected error: {exc}",
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
