"""Tests for execution visibility query service."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.proof_artifact import ProofArtifact
from app.services import execution_query


async def _seed_attempt(db: AsyncSession, tenant_id: str, attempt_id_key: str, status: str = "running") -> ApplicationAttempt:
    attempt = ApplicationAttempt(
        tenant_id=tenant_id,
        application_id=f"app-{attempt_id_key}",
        workflow_run_id=f"wf-{attempt_id_key}",
        candidate_id=f"cand-{attempt_id_key}",
        job_id=f"job-{attempt_id_key}",
        status=status,
        idempotency_key=f"idem-{attempt_id_key}",
        attempt_number=1,
        manual_checkpoint_required=(status == "waiting_manual"),
    )
    db.add(attempt)
    await db.flush()

    step = ApplicationAttemptStep(
        tenant_id=tenant_id,
        attempt_id=attempt.id,
        step_name="submit",
        sequence_number=1,
        status="completed",
        idempotency_key=f"idem-step-{attempt_id_key}",
    )
    db.add(step)
    await db.flush()

    artifact = ProofArtifact(
        tenant_id=tenant_id,
        attempt_id=attempt.id,
        attempt_step_id=step.id,
        artifact_type="log",
        storage_path=f"attempt://{attempt.id}/log",
    )
    db.add(artifact)
    await db.commit()
    return attempt


class TestExecutionQueryService:
    async def test_list_attempts_is_tenant_scoped(self, db_session: AsyncSession) -> None:
        await _seed_attempt(db_session, "tenant-1", "1")
        await _seed_attempt(db_session, "tenant-2", "2")

        auth = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.OPERATOR, enforced=True)
        resp = await execution_query.list_attempts(db_session, auth)

        assert resp.total == 1
        assert resp.items[0].tenant_id == "tenant-1"

    async def test_manual_and_retry_queue_filters(self, db_session: AsyncSession) -> None:
        await _seed_attempt(db_session, "tenant-1", "m", status="waiting_manual")
        await _seed_attempt(db_session, "tenant-1", "r", status="failed_retryable")

        auth = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.OPERATOR, enforced=True)
        manual = await execution_query.list_manual_queue(db_session, auth)
        retry = await execution_query.list_retry_queue(db_session, auth)

        assert all(item.status == "waiting_manual" for item in manual.items)
        assert all(item.status in {"failed_retryable", "retry_scheduled"} for item in retry.items)

    async def test_attempt_steps_and_artifacts_tenant_safe(self, db_session: AsyncSession) -> None:
        attempt = await _seed_attempt(db_session, "tenant-1", "3")

        auth = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.REVIEWER, enforced=True)
        steps = await execution_query.list_attempt_steps(db_session, auth, attempt.id)
        artifacts = await execution_query.list_attempt_artifacts(db_session, auth, attempt.id)

        assert len(steps) == 1
        assert len(artifacts.items) == 1
