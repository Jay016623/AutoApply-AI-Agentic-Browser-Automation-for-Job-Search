"""Unit tests for execution visibility persistence/query behavior."""

from datetime import UTC, datetime, timedelta

from app.models.application import Application
from app.models.job import Job
from app.schemas.application import ApplicationCreate
from app.services import application as application_service
from app.services import execution_visibility as visibility_service


async def _create_application(db_session, sample_job_data, tenant_id: str = "tenant-1") -> Application:
    job = Job(**{**sample_job_data, "tenant_id": tenant_id})
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return await application_service.create_application(
        db_session,
        ApplicationCreate(job_id=job.id, tenant_id=tenant_id),
    )


class TestExecutionVisibilityService:
    async def test_attempt_step_artifact_checkpoint_flow(self, db_session, sample_job_data):
        app = await _create_application(db_session, sample_job_data, tenant_id="tenant-1")

        attempt = await visibility_service.start_attempt(
            db_session,
            tenant_id="tenant-1",
            application_id=app.id,
            candidate_id=None,
            trigger_reason="approve",
            execution_task_id="task-1",
            worker_trace_id="trace-1",
        )
        step = await visibility_service.start_step(
            db_session,
            tenant_id="tenant-1",
            attempt_id=attempt.id,
            application_id=app.id,
            step_name="load_context",
            step_order=1,
        )
        await visibility_service.complete_step(db_session, step_id=step.id)

        artifact = await visibility_service.record_proof_artifact(
            db_session,
            tenant_id="tenant-1",
            application_id=app.id,
            attempt_id=attempt.id,
            step_id=step.id,
            artifact_type="generated_resume",
            storage_uri="/tmp/fake.pdf",
            metadata_json={"resume_id": "r1"},
        )
        checkpoint = await visibility_service.create_manual_checkpoint(
            db_session,
            tenant_id="tenant-1",
            application_id=app.id,
            attempt_id=attempt.id,
            step_id=step.id,
            checkpoint_type="unsupported_form",
            reason_code="UNSUPPORTED_FORM",
            reason_message="Unsupported form layout detected.",
            blocker_confidence="high",
        )
        finalized = await visibility_service.finalize_attempt(
            db_session,
            attempt_id=attempt.id,
            status=visibility_service.ATTEMPT_STATUS_INTERRUPTED,
            error_code="UNSUPPORTED_FORM",
            error_message="Unsupported form layout detected.",
        )

        assert artifact.application_id == app.id
        assert checkpoint.reason_code == "UNSUPPORTED_FORM"
        assert finalized.status == visibility_service.ATTEMPT_STATUS_INTERRUPTED

    async def test_tenant_scoped_filters(self, db_session, sample_job_data):
        app1 = await _create_application(db_session, sample_job_data, tenant_id="tenant-a")
        app2 = await _create_application(
            db_session,
            {**sample_job_data, "platform_job_id": "job-tenant-b"},
            tenant_id="tenant-b",
        )

        attempt1 = await visibility_service.start_attempt(
            db_session,
            tenant_id="tenant-a",
            application_id=app1.id,
            candidate_id="cand-1",
            trigger_reason="approve",
            execution_task_id="task-a",
            worker_trace_id="trace-a",
        )
        await visibility_service.start_attempt(
            db_session,
            tenant_id="tenant-b",
            application_id=app2.id,
            candidate_id="cand-2",
            trigger_reason="approve",
            execution_task_id="task-b",
            worker_trace_id="trace-b",
        )

        attempts = await visibility_service.list_attempts(
            db_session,
            tenant_id="tenant-a",
            candidate_id="cand-1",
        )
        assert len(attempts) == 1
        assert attempts[0].id == attempt1.id

        steps = await visibility_service.list_steps(
            db_session,
            tenant_id="tenant-a",
            created_from=datetime.now(UTC) - timedelta(days=1),
            created_to=datetime.now(UTC) + timedelta(days=1),
        )
        assert isinstance(steps, list)
