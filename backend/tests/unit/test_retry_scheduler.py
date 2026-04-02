"""Tests for retry scheduler queue dispatch and escalation behavior."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.job import Job
from app.services import retry_scheduler


class DummyRedis:
    pass


async def _seed_retry_attempt(db_session: AsyncSession, status: str, retry_count: int = 0) -> ApplicationAttempt:
    job = Job(
        tenant_id="tenant-1",
        platform="linkedin",
        platform_job_id=f"job-{status}-{retry_count}",
        title="Engineer",
        company="ACME",
        location="Remote",
        url="https://example.com/job",
        description="desc",
        status="new",
    )
    db_session.add(job)
    await db_session.flush()

    app = Application(
        tenant_id="tenant-1",
        job_id=job.id,
        status="queued",
        apply_mode="review",
    )
    db_session.add(app)
    await db_session.flush()

    attempt = ApplicationAttempt(
        tenant_id="tenant-1",
        application_id=app.id,
        workflow_run_id=None,
        candidate_id="cand-1",
        job_id=job.id,
        status=status,
        idempotency_key=f"idem-{status}-{retry_count}",
        attempt_number=1,
        retry_count=retry_count,
        next_retry_at=(datetime.now(UTC) - timedelta(seconds=1)) if status == "retry_scheduled" else None,
    )
    db_session.add(attempt)
    await db_session.commit()
    return attempt


class TestRetryScheduler:
    async def test_schedules_failed_retryable_attempt(self, db_session: AsyncSession, monkeypatch) -> None:
        await _seed_retry_attempt(db_session, "failed_retryable", retry_count=0)

        async def _noop_enqueue(*_args, **_kwargs):
            return "task-1"

        monkeypatch.setattr(retry_scheduler, "enqueue", _noop_enqueue)

        metrics = await retry_scheduler.run_retry_cycle(DummyRedis(), max_retries=3)
        assert metrics["scheduled"] == 1

        rows = (await db_session.execute(select(ApplicationAttempt))).scalars().all()
        assert rows[0].status == "retry_scheduled"
        assert rows[0].next_retry_at is not None

    async def test_dispatches_due_retry(self, db_session: AsyncSession, monkeypatch) -> None:
        attempt = await _seed_retry_attempt(db_session, "retry_scheduled", retry_count=1)
        captured = {}

        async def _capture_enqueue(_redis, _queue, payload):
            captured.update(payload)
            return "task-2"

        monkeypatch.setattr(retry_scheduler, "enqueue", _capture_enqueue)

        metrics = await retry_scheduler.run_retry_cycle(DummyRedis(), max_retries=3)
        assert metrics["dispatched"] == 1
        assert captured["application_id"] == attempt.application_id

    async def test_escalates_when_retry_limit_exhausted(self, db_session: AsyncSession, monkeypatch) -> None:
        await _seed_retry_attempt(db_session, "failed_retryable", retry_count=3)

        async def _noop_enqueue(*_args, **_kwargs):
            return "task-3"

        monkeypatch.setattr(retry_scheduler, "enqueue", _noop_enqueue)

        metrics = await retry_scheduler.run_retry_cycle(DummyRedis(), max_retries=3)
        assert metrics["manual_escalated"] == 1

        rows = (await db_session.execute(select(ApplicationAttempt))).scalars().all()
        assert rows[0].status == "waiting_manual"
