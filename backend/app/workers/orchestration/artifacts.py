"""Proof/artifact orchestration for worker apply flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select

from app.models.resume import Resume
from app.schemas.resume import ResumeGenerateRequest
from app.services.feedback_loop import get_feedback_loop_adjustments
from app.services.resume_selection import select_best_resume_for_job

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GeneratedArtifacts:
    """Paths to generated artifacts used during submission."""

    resume_path: str | None = None
    resume_id: str | None = None
    decision_reason: str = ""


@dataclass
class ArtifactOrchestrator:
    """Generate and resolve submission artifacts for a queued application."""

    session_factory: Callable
    resume_service: object

    async def generate_for_application(
        self,
        *,
        job_id: str,
        resume_id: str,
        tenant_id: str | None = None,
    ) -> GeneratedArtifacts:
        """Generate tailored resume artifacts when base resume is present."""
        if not resume_id:
            return GeneratedArtifacts()

        try:
            async with self.session_factory() as db:
                feedback = await get_feedback_loop_adjustments(db, tenant_id=tenant_id)
                decision = await select_best_resume_for_job(
                    db,
                    base_resume_id=resume_id,
                    job_id=job_id,
                    max_tailored_versions_per_job=feedback.max_tailored_versions_per_job,
                    base_fit_keep_threshold=feedback.base_fit_keep_threshold,
                )

                selected = decision.selected_resume
                if selected is None:
                    return GeneratedArtifacts(decision_reason=decision.reason)

                if not decision.should_tailor:
                    return GeneratedArtifacts(
                        resume_path=selected.file_path_pdf or selected.file_path_docx,
                        resume_id=selected.id,
                        decision_reason=decision.reason,
                    )

                gen_request = ResumeGenerateRequest(
                    base_resume_id=selected.id,
                    job_id=job_id,
                    template_id="modern",
                )
                tailored_resp = await self.resume_service.generate_tailored_resume(
                    db,
                    gen_request,
                )
                result = await db.execute(select(Resume).where(Resume.id == tailored_resp.id))
                tailored_resume = result.scalar_one_or_none()

            if tailored_resume is None:
                return GeneratedArtifacts(
                    resume_path=selected.file_path_pdf or selected.file_path_docx,
                    resume_id=selected.id,
                    decision_reason="tailor_missing_fallback_selected",
                )

            return GeneratedArtifacts(
                resume_path=tailored_resume.file_path_pdf or tailored_resume.file_path_docx,
                resume_id=tailored_resume.id,
                decision_reason=decision.reason,
            )
        except Exception as exc:
            logger.warning(
                "artifacts.resume_generation_failed",
                job_id=job_id,
                resume_id=resume_id,
                error=str(exc),
            )
            return GeneratedArtifacts(decision_reason="exception_fallback")
