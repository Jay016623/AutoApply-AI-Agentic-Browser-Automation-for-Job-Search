"""Tenant isolation tests for application service."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.models.job import Job
from app.schemas.application import ApplicationCreate
from app.services import application as application_service


@pytest.mark.asyncio
async def test_list_applications_scoped_by_tenant(db_session: AsyncSession, sample_job_data: dict) -> None:
    job = Job(**sample_job_data)
    db_session.add(job)
    await db_session.commit()

    auth_t1 = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.ADMIN, enforced=False)
    auth_t2 = AuthContext(user_id="u2", tenant_id="tenant-2", role=Role.ADMIN, enforced=False)

    await application_service.create_application(
        db_session,
        ApplicationCreate(job_id=job.id, tenant_id="tenant-1"),
        auth_t1,
    )
    await application_service.create_application(
        db_session,
        ApplicationCreate(job_id=job.id, tenant_id="tenant-2"),
        auth_t2,
    )

    list_t1 = await application_service.list_applications(db_session, auth_t1)
    assert all(item.tenant_id == "tenant-1" for item in list_t1.items)
