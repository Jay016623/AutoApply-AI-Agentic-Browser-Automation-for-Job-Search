"""Queue-backed retry scheduler for failed retryable attempts."""

from datetime import UTC, datetime, timedelta
import uuid

import structlog
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import QUEUE_APPLY
from app.db.session import async_session_factory
from app.domains.applications.execution import ApplicationAttemptService
from app.domains.applications.workflow.retry_policy import exponential_backoff_delay
from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.job import Job
from app.observability.metrics import retry_events_total
from app.services.queue import build_envelope, enqueue_envelope

logger = structlog.get_logger(__name__)


MAX_RETRIES = 3
SCHEDULER_LOCK_KEY = "autoapply:lock:retry_scheduler"
SCHEDULER_LOCK_TTL_SECONDS = 20


async def run_retry_cycle(redis: Redis, max_retries: int = MAX_RETRIES, batch_size: int = 50) -> dict[str, int]:
    """Schedule and dispatch retries for retryable attempts."""
    lock_token = uuid.uuid4().hex
    acquired = await redis.set(SCHEDULER_LOCK_KEY, lock_token, ex=SCHEDULER_LOCK_TTL_SECONDS, nx=True)
    if not acquired:
        logger.debug("retry_scheduler.lock_not_acquired")
        retry_events_total.labels(event_type="lock_skip", status="not_acquired").inc()
        return {"scheduled": 0, "dispatched": 0, "manual_escalated": 0}

    now = datetime.now(UTC)
    scheduled = 0
    dispatched = 0
    manual_escalated = 0

    try:
        async with async_session_factory() as db:
            attempts_result = await db.execute(
                select(ApplicationAttempt)
                .where(ApplicationAttempt.status.in_(["failed_retryable", "retry_scheduled"]))
                .order_by(ApplicationAttempt.updated_at.asc())
                .limit(batch_size),
            )
            attempts = list(attempts_result.scalars().all())

            for attempt in attempts:
                service = ApplicationAttemptService(db, tenant_scope=attempt.tenant_id)

                if attempt.status == "failed_retryable":
                    delay = exponential_backoff_delay(attempt.retry_count + 1)
                    next_retry_at = now + timedelta(seconds=delay)
                    updated = await service.schedule_retry(
                        attempt.id,
                        next_retry_at=next_retry_at,
                        max_retries=max_retries,
                    )
                    if updated.status == "waiting_manual":
                        manual_escalated += 1
                        retry_events_total.labels(event_type="retry_schedule", status="manual_escalated").inc()
                    else:
                        scheduled += 1
                        retry_events_total.labels(event_type="retry_schedule", status="scheduled").inc()
                    continue

                if attempt.status == "retry_scheduled" and attempt.next_retry_at and attempt.next_retry_at <= now:
                    payload = await _build_retry_payload(db, attempt)
                    if payload is None:
                        await service.schedule_retry(
                            attempt.id,
                            next_retry_at=now,
                            max_retries=0,
                        )
                        manual_escalated += 1
                        retry_events_total.labels(event_type="retry_dispatch", status="manual_escalated").inc()
                        continue

                    payload["execution_idempotency_key"] = attempt.id
                    envelope = build_envelope(
                        payload=payload,
                        tenant_id=attempt.tenant_id,
                        attempt_id=attempt.id,
                        idempotency_key=attempt.id,
                        retry_count=attempt.retry_count,
                        max_retries=max_retries,
                    )
                    task_id = await enqueue_envelope(redis, QUEUE_APPLY, envelope)
                    if task_id:
                        await service.mark_retry_dispatched(attempt.id)
                        dispatched += 1
                        retry_events_total.labels(event_type="retry_dispatch", status="dispatched").inc()
                    else:
                        retry_events_total.labels(event_type="retry_dispatch", status="duplicate_rejected").inc()
    finally:
        current_token = await redis.get(SCHEDULER_LOCK_KEY)
        if current_token is not None and current_token.decode("utf-8") == lock_token:
            await redis.delete(SCHEDULER_LOCK_KEY)

    logger.info(
        "retry_scheduler.cycle_completed",
        scheduled=scheduled,
        dispatched=dispatched,
        manual_escalated=manual_escalated,
        max_retries=max_retries,
        batch_size=batch_size,
    )
    return {
        "scheduled": scheduled,
        "dispatched": dispatched,
        "manual_escalated": manual_escalated,
    }


async def _build_retry_payload(db: AsyncSession, attempt: ApplicationAttempt) -> dict | None:
    app_result = await db.execute(select(Application).where(Application.id == attempt.application_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        return None

    job_result = await db.execute(select(Job).where(Job.id == app.job_id))
    job = job_result.scalar_one_or_none()
    if job is None:
        return None

    return {
        "job_id": app.job_id,
        "application_id": app.id,
        "resume_id": app.resume_id or "",
        "platform": job.platform,
        "tenant_id": attempt.tenant_id,
        "candidate_id": attempt.candidate_id,
    }
