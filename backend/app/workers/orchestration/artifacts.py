"""Proof/artifact orchestration for worker apply flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select

from app.models.resume import Resume
from app.schemas.resume import ResumeGenerateRequest

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class GeneratedArtifacts:
    """Paths to generated artifacts used during submission."""

    resume_path: str | None = None


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
    ) -> GeneratedArtifacts:
        """Generate tailored resume artifacts when base resume is present."""
        if not resume_id:
            return GeneratedArtifacts()

        try:
            async with self.session_factory() as db:
                gen_request = ResumeGenerateRequest(
                    base_resume_id=resume_id,
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
                return GeneratedArtifacts()

            return GeneratedArtifacts(
                resume_path=tailored_resume.file_path_pdf or tailored_resume.file_path_docx,
            )
        except Exception as exc:
            logger.warning(
                "artifacts.resume_generation_failed",
                job_id=job_id,
                resume_id=resume_id,
                error=str(exc),
            )
            return GeneratedArtifacts()
