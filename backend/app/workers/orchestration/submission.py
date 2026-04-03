"""Submission orchestration for worker apply flow."""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from app.core.automation.platforms.base import JobListing

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class SubmissionResult:
    """Outcome of a platform submission attempt."""

    success: bool
    error: str = ""


@dataclass
class SubmissionOrchestrator:
    """Encapsulates platform-application submission calls."""

    platform_registry: object

    async def submit(
        self,
        *,
        platform_name: str,
        job: JobListing,
        resume_path: str,
        cover_letter_path: str | None,
    ) -> SubmissionResult:
        """Submit to platform and normalize result shape."""
        try:
            platform = self.platform_registry.create(platform_name)
        except KeyError as exc:
            return SubmissionResult(success=False, error=f"Platform creation failed: {exc}")

        try:
            applied = await platform.apply(
                job=job,
                resume_path=resume_path,
                cover_letter_path=cover_letter_path,
            )
            if not applied:
                return SubmissionResult(
                    success=False,
                    error="Platform returned unsuccessful apply result",
                )
            return SubmissionResult(success=True)
        except Exception as exc:
            logger.error(
                "submission.submit_failed",
                platform=platform_name,
                job_id=job.platform_job_id,
                error=str(exc),
            )
            return SubmissionResult(
                success=False,
                error=f"Application submission failed: {exc}",
            )
