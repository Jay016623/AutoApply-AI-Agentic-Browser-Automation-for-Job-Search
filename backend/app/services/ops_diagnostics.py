"""Operational diagnostics helpers for readiness and incident response."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from redis.asyncio import Redis
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import QUEUE_APPLY, QUEUE_APPLY_DEAD_LETTER, QUEUE_GENERATE, QUEUE_SCRAPE
from app.models.application_attempt import ApplicationAttempt
from app.models.review_task import ReviewTask
from app.services.artifacts import get_artifact_storage
from app.services.queue import get_queue_depth


@dataclass(frozen=True)
class DependencyCheck:
    status: str
    latency_ms: float
    details: str = ""


async def check_database(db: AsyncSession) -> DependencyCheck:
    start = datetime.now(UTC)
    try:
        await db.execute(text("SELECT 1"))
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="ok", latency_ms=latency_ms)
    except Exception as exc:  # noqa: BLE001
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="down", latency_ms=latency_ms, details=str(exc))


async def check_redis(redis: Redis | None) -> DependencyCheck:
    start = datetime.now(UTC)
    if redis is None:
        return DependencyCheck(status="down", latency_ms=0.0, details="redis_client_unavailable")
    try:
        await redis.ping()
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="ok", latency_ms=latency_ms)
    except Exception as exc:  # noqa: BLE001
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="down", latency_ms=latency_ms, details=str(exc))


async def check_artifact_backend() -> DependencyCheck:
    start = datetime.now(UTC)
    try:
        storage = get_artifact_storage()
        healthy, details = await storage.check_health()
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="ok" if healthy else "down", latency_ms=latency_ms, details=details)
    except Exception as exc:  # noqa: BLE001
        latency_ms = (datetime.now(UTC) - start).total_seconds() * 1000
        return DependencyCheck(status="down", latency_ms=latency_ms, details=str(exc))


async def queue_depth_snapshot(redis: Redis | None) -> dict[str, int]:
    if redis is None:
        return {
            QUEUE_APPLY: 0,
            QUEUE_APPLY_DEAD_LETTER: 0,
            QUEUE_SCRAPE: 0,
            QUEUE_GENERATE: 0,
        }

    return {
        QUEUE_APPLY: await get_queue_depth(redis, QUEUE_APPLY),
        QUEUE_APPLY_DEAD_LETTER: await get_queue_depth(redis, QUEUE_APPLY_DEAD_LETTER),
        QUEUE_SCRAPE: await get_queue_depth(redis, QUEUE_SCRAPE),
        QUEUE_GENERATE: await get_queue_depth(redis, QUEUE_GENERATE),
    }


async def workflow_pressure_snapshot(db: AsyncSession) -> dict[str, int]:
    retry_backlog = int(
        (
            await db.execute(
                select(func.count(ApplicationAttempt.id)).where(
                    ApplicationAttempt.status.in_(["failed_retryable", "retry_scheduled"]),
                ),
            )
        ).scalar()
        or 0
    )
    open_reviews = int((await db.execute(select(func.count(ReviewTask.id)).where(ReviewTask.status == "open"))).scalar() or 0)
    return {
        "retry_backlog": retry_backlog,
        "open_reviews": open_reviews,
    }
