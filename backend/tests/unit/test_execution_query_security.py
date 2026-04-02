"""Security-focused tests for execution query services."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.core.exceptions import RecordNotFoundError
from app.models.application_attempt import ApplicationAttempt
from app.models.proof_artifact import ProofArtifact
from app.services import execution_query


async def _seed_artifact(db: AsyncSession, tenant_id: str) -> str:
    attempt = ApplicationAttempt(
        tenant_id=tenant_id,
        application_id=f"app-{tenant_id}",
        workflow_run_id=f"wf-{tenant_id}",
        status="running",
        idempotency_key=f"idem-{tenant_id}",
        attempt_number=1,
    )
    db.add(attempt)
    await db.flush()
    artifact = ProofArtifact(
        tenant_id=tenant_id,
        application_id=attempt.application_id,
        workflow_run_id=attempt.workflow_run_id,
        attempt_id=attempt.id,
        artifact_type="trace",
        storage_path=f"attempt://{attempt.id}/trace",
        storage_backend="local",
    )
    db.add(artifact)
    await db.commit()
    return artifact.id


class TestExecutionQuerySecurity:
    async def test_download_url_is_tenant_scoped(self, db_session: AsyncSession):
        artifact_id = await _seed_artifact(db_session, "tenant-1")

        allowed = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.OPERATOR, enforced=True)
        denied = AuthContext(user_id="u2", tenant_id="tenant-2", role=Role.OPERATOR, enforced=True)

        ok = await execution_query.get_artifact_download_url(db_session, allowed, artifact_id)
        assert ok.artifact_id == artifact_id

        with pytest.raises(RecordNotFoundError):
            await execution_query.get_artifact_download_url(db_session, denied, artifact_id)
