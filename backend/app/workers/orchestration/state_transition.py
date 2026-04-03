"""State transition orchestration for worker-driven apply flow."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from app.config.constants import ApplicationStatus


@dataclass(frozen=True)
class StateTransitionOrchestrator:
    """Encapsulates status persistence + websocket progress emission."""

    update_status: Callable[..., Awaitable[None]]
    broadcast_progress: Callable[[str, str, str], Awaitable[None]]

    async def progress(
        self,
        application_id: str,
        status: str,
        detail: str = "",
    ) -> None:
        """Emit a progress event only."""
        await self.broadcast_progress(application_id, status, detail)

    async def fail(
        self,
        application_id: str,
        *,
        detail: str,
        notes: str | None = None,
        ats_score: float | None = None,
    ) -> None:
        """Persist failed state and emit failure event."""
        await self.update_status(
            application_id,
            ApplicationStatus.FAILED,
            notes=notes if notes is not None else detail,
            ats_score=ats_score,
        )
        await self.broadcast_progress(
            application_id,
            ApplicationStatus.FAILED,
            detail,
        )

    async def applied(
        self,
        application_id: str,
        *,
        ats_score: float | None,
        applied_at: datetime,
    ) -> None:
        """Persist applied state and emit applied event."""
        await self.update_status(
            application_id,
            ApplicationStatus.APPLIED,
            ats_score=ats_score,
            applied_at=applied_at,
        )
        await self.broadcast_progress(application_id, ApplicationStatus.APPLIED, "")
