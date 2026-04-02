"""Tenant safety tests for jobs and application linkage."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.models.job import Job
from app.schemas.application import ApplicationCreate
from app.services import application as application_service
from app.services import job_search as job_service


@pytest.mark.asyncio
async def test_job_list_is_tenant_scoped(db_session: AsyncSession, sample_job_data: dict) -> None:
    job1 = Job(**sample_job_data, tenant_id="tenant-1")
    job2 = Job(**{**sample_job_data, "platform_job_id": "job-2", "tenant_id": "tenant-2"})
    db_session.add_all([job1, job2])
    await db_session.commit()

    auth = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.RECRUITER, enforced=False)
    listed = await job_service.list_jobs(db_session, auth)

    assert listed.total >= 1
    assert all(item.tenant_id == "tenant-1" for item in listed.items)


@pytest.mark.asyncio
async def test_application_job_tenant_mismatch_rejected(db_session: AsyncSession, sample_job_data: dict) -> None:
    job = Job(**sample_job_data, tenant_id="tenant-2")
    db_session.add(job)
    await db_session.commit()

    auth = AuthContext(user_id="u1", tenant_id="tenant-1", role=Role.ADMIN, enforced=True)
    with pytest.raises(ValueError):
        await application_service.create_application(
            db_session,
            ApplicationCreate(job_id=job.id, tenant_id="tenant-1"),
            auth,
        )
