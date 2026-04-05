"""Unit tests for the application service."""

import pytest
from unittest.mock import AsyncMock, patch

from app.config.constants import ApplicationStatus
from app.core.exceptions import RecordNotFoundError
from app.models.job import Job
from app.schemas.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationStatusUpdate,
)
from app.services import application as app_service


async def _create_job(db_session, sample_job_data, suffix="0"):
    """Helper to create a job and return it."""
    data = {**sample_job_data, "platform_job_id": f"job-{suffix}"}
    job = Job(**data)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


class TestCreateApplication:
    async def test_create_application(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        data = ApplicationCreate(job_id=job.id)
        app = await app_service.create_application(db_session, data)

        assert app.id is not None
        assert app.job_id == job.id
        assert app.status == ApplicationStatus.PENDING_REVIEW
        assert app.apply_mode == "review"
        assert app.resume_id is None

    async def test_create_application_autonomous_enqueues(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        data = ApplicationCreate(job_id=job.id, apply_mode="autonomous", tenant_id="tenant-1")

        with (
            patch("app.services.application.get_redis") as mock_get_redis,
            patch(
                "app.services.application.enqueue_idempotent",
                new_callable=AsyncMock,
            ) as mock_enqueue_idempotent,
        ):
            mock_get_redis.return_value = object()
            mock_enqueue_idempotent.return_value = ("task-1", True)
            app = await app_service.create_application(db_session, data)

        assert app.execution_task_id == "task-1"
        assert app.tenant_id == "tenant-1"
        assert mock_enqueue_idempotent.await_count == 1

    async def test_create_application_autonomous_requires_tenant(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        data = ApplicationCreate(job_id=job.id, apply_mode="autonomous")
        with pytest.raises(ValueError, match="Tenant context is required for autonomous"):
            await app_service.create_application(db_session, data)


class TestCreateBatch:
    async def test_create_batch(self, db_session, sample_job_data):
        jobs = []
        for i in range(3):
            jobs.append(await _create_job(db_session, sample_job_data, suffix=str(i)))

        data = ApplicationBatchCreate(job_ids=[j.id for j in jobs])
        apps = await app_service.create_batch(db_session, data)

        assert len(apps) == 3
        job_ids = {a.job_id for a in apps}
        assert job_ids == {j.id for j in jobs}
        assert all(a.status == ApplicationStatus.PENDING_REVIEW for a in apps)


class TestListApplications:
    async def test_list_applications_empty(self, db_session):
        result = await app_service.list_applications(db_session)
        assert result.items == []
        assert result.total == 0

    async def test_list_applications_with_data(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        for _ in range(3):
            data = ApplicationCreate(job_id=job.id)
            await app_service.create_application(db_session, data)

        result = await app_service.list_applications(db_session, page=1, page_size=2)
        assert len(result.items) == 2
        assert result.total == 3
        assert result.has_next is True

    async def test_list_applications_filter_status(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)

        # Create two QUEUED apps
        for _ in range(2):
            await app_service.create_application(
                db_session, ApplicationCreate(job_id=job.id)
            )

        # Create one and approve it
        app_obj = await app_service.create_application(
            db_session, ApplicationCreate(job_id=job.id)
        )
        with patch("app.services.application.get_redis") as mock_get_redis:
            mock_get_redis.return_value = None
            await app_service.approve_application(db_session, app_obj.id)

        queued = await app_service.list_applications(
            db_session, status=ApplicationStatus.QUEUED
        )
        assert queued.total == 0

        approved = await app_service.list_applications(
            db_session, status=ApplicationStatus.APPROVED
        )
        assert approved.total == 1


class TestGetApplication:
    async def test_get_application_found(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session, ApplicationCreate(job_id=job.id)
        )

        found = await app_service.get_application(db_session, created.id)
        assert found.id == created.id
        assert found.job_id == job.id

    async def test_get_application_not_found(self, db_session):
        with pytest.raises(RecordNotFoundError):
            await app_service.get_application(db_session, "nonexistent_id")


class TestApproveApplication:
    async def test_approve_application(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session, ApplicationCreate(job_id=job.id)
        )
        assert created.status == ApplicationStatus.PENDING_REVIEW

        with patch("app.services.application.get_redis") as mock_get_redis:
            mock_get_redis.return_value = None
            approved = await app_service.approve_application(db_session, created.id)
        assert approved.status == ApplicationStatus.APPROVED

    async def test_repeated_approval_does_not_duplicate_enqueue(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session,
            ApplicationCreate(job_id=job.id, tenant_id="tenant-1"),
        )

        with (
            patch("app.services.application.get_redis") as mock_get_redis,
            patch(
                "app.services.application.enqueue_idempotent",
                new_callable=AsyncMock,
            ) as mock_enqueue_idempotent,
        ):
            mock_get_redis.return_value = object()
            mock_enqueue_idempotent.return_value = ("task-repeat", True)
            first = await app_service.approve_application(
                db_session,
                created.id,
                tenant_id="tenant-1",
            )
            second = await app_service.approve_application(
                db_session,
                created.id,
                tenant_id="tenant-1",
            )

        assert first.execution_task_id == "task-repeat"
        assert second.execution_task_id == "task-repeat"
        assert mock_enqueue_idempotent.await_count == 1

    async def test_repeated_approval_uses_stable_task_when_enqueue_suppressed(
        self, db_session, sample_job_data,
    ):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session,
            ApplicationCreate(job_id=job.id, tenant_id="tenant-1"),
        )

        with (
            patch("app.services.application.get_redis") as mock_get_redis,
            patch(
                "app.services.application.enqueue_idempotent",
                new_callable=AsyncMock,
            ) as mock_enqueue_idempotent,
        ):
            mock_get_redis.return_value = object()
            mock_enqueue_idempotent.return_value = ("task-stable", False)
            approved = await app_service.approve_application(
                db_session,
                created.id,
                tenant_id="tenant-1",
            )

        assert approved.execution_task_id == "task-stable"
        assert approved.status == ApplicationStatus.QUEUED

    async def test_approve_application_requires_tenant_for_execution(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session,
            ApplicationCreate(job_id=job.id),
        )
        with pytest.raises(ValueError, match="Tenant context is required for approval"):
            await app_service.approve_application(db_session, created.id)


class TestUpdateStatus:
    async def test_update_status_with_notes(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session, ApplicationCreate(job_id=job.id)
        )

        update = ApplicationStatusUpdate(status=ApplicationStatus.REJECTED, notes="Not a fit")
        updated = await app_service.update_status(db_session, created.id, update)

        assert updated.status == ApplicationStatus.REJECTED
        assert updated.notes == "Not a fit"

    async def test_update_status_applied_sets_timestamp(self, db_session, sample_job_data):
        job = await _create_job(db_session, sample_job_data)
        created = await app_service.create_application(
            db_session, ApplicationCreate(job_id=job.id)
        )
        assert created.applied_at is None

        update = ApplicationStatusUpdate(status=ApplicationStatus.APPLIED)
        updated = await app_service.update_status(db_session, created.id, update)

        assert updated.status == ApplicationStatus.APPLIED
        assert updated.applied_at is not None
