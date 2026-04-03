"""Verification orchestration for worker apply flow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import structlog
from sqlalchemy import select

from app.models.job import Job

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class VerificationResult:
    """Result of a verification step."""

    ok: bool
    error: str = ""


@dataclass
class VerificationOrchestrator:
    """Container for platform/job/threshold verification logic."""

    session_factory: Callable
    platform_registry: object

    def verify_platform(self, platform_name: str) -> VerificationResult:
        """Verify platform exists in registry."""
        if not getattr(self.platform_registry, "has")(platform_name):
            return VerificationResult(
                ok=False,
                error=f"Unknown platform: {platform_name}",
            )
        return VerificationResult(ok=True)

    async def load_job(self, job_id: str) -> Job | None:
        """Load job from DB via session factory."""
        try:
            async with self.session_factory() as db:
                result = await db.execute(select(Job).where(Job.id == job_id))
                return result.scalar_one_or_none()
        except Exception as exc:
            logger.error("verification.load_job_failed", job_id=job_id, error=str(exc))
            return None

    @staticmethod
    def verify_ats_threshold(
        ats_score: float | None,
        min_score: float,
    ) -> VerificationResult:
        """Validate ATS threshold requirement."""
        if ats_score is not None and ats_score < min_score:
            return VerificationResult(
                ok=False,
                error=(
                    f"ATS score {ats_score:.2f} below minimum "
                    f"threshold {min_score:.2f}"
                ),
            )
        return VerificationResult(ok=True)
