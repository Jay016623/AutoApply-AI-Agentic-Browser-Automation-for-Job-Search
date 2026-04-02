"""Unit tests for control-plane plan/quota enforcement."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate import Candidate
from app.models.tenant import Tenant
from app.services import control_plane


class TestControlPlane:
    async def test_plan_snapshot_defaults_to_free(self, db_session: AsyncSession):
        tenant = Tenant(name="Acme", slug="acme")
        db_session.add(tenant)
        await db_session.commit()

        snapshot = await control_plane.get_tenant_plan_snapshot(db_session, tenant.id)
        assert snapshot.plan_key == "free"
        assert snapshot.quotas["candidate_count"] == 5

    async def test_candidate_quota_enforced(self, db_session: AsyncSession):
        tenant = Tenant(name="Tiny", slug="tiny", plan_key="free", plan_overrides={"candidate_count": 1})
        db_session.add(tenant)
        await db_session.flush()

        db_session.add(
            Candidate(
                tenant_id=tenant.id,
                full_name="First",
                email="first@example.com",
                settings={},
            ),
        )
        await db_session.commit()

        with pytest.raises(control_plane.QuotaExceededError):
            await control_plane.enforce_quota(
                db_session,
                tenant_id=tenant.id,
                quota_key="candidate_count",
                increment=1,
                context={"test": True},
            )

    async def test_feature_override_enables_premium_capability(self, db_session: AsyncSession):
        tenant = Tenant(
            name="Custom",
            slug="custom",
            plan_key="free",
            feature_overrides={"advanced_execution_diagnostics": True},
        )
        db_session.add(tenant)
        await db_session.commit()

        await control_plane.require_feature(
            db_session,
            tenant_id=tenant.id,
            feature_key="advanced_execution_diagnostics",
        )
