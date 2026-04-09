"""Integration tests for application visibility API endpoints."""

from app.models.job import Job
from app.schemas.application import ApplicationCreate
from app.services import application as application_service
from app.services import execution_visibility as visibility_service

API_PREFIX = "/api/v1/applications"


async def _seed_attempt(db_session, sample_job_data, tenant_id: str, task_id: str):
    job = Job(**{**sample_job_data, "platform_job_id": f"job-{tenant_id}", "tenant_id": tenant_id})
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)

    app = await application_service.create_application(
        db_session,
        ApplicationCreate(job_id=job.id, tenant_id=tenant_id),
    )
    attempt = await visibility_service.start_attempt(
        db_session,
        tenant_id=tenant_id,
        application_id=app.id,
        candidate_id=None,
        trigger_reason="approve",
        execution_task_id=task_id,
        worker_trace_id=f"trace-{tenant_id}",
    )
    step = await visibility_service.start_step(
        db_session,
        tenant_id=tenant_id,
        attempt_id=attempt.id,
        application_id=app.id,
        step_name="load_context",
        step_order=1,
    )
    await visibility_service.complete_step(db_session, step_id=step.id)
    return app, attempt, step


class TestApplicationVisibilityApi:
    async def test_attempts_and_steps_are_tenant_scoped(self, client, db_session, sample_job_data):
        _, attempt_a, _ = await _seed_attempt(db_session, sample_job_data, "tenant-a", "task-a")
        await _seed_attempt(
            db_session,
            {**sample_job_data, "platform_job_id": "job-tenant-b"},
            "tenant-b",
            "task-b",
        )

        resp = await client.get(
            f"{API_PREFIX}/attempts",
            headers={"X-Tenant-Id": "tenant-a"},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["id"] == attempt_a.id

        detail = await client.get(
            f"{API_PREFIX}/attempts/{attempt_a.id}",
            headers={"X-Tenant-Id": "tenant-a"},
        )
        assert detail.status_code == 200
        assert detail.json()["execution_task_id"] == "task-a"

    async def test_manual_checkpoint_list_detail(self, client, db_session, sample_job_data):
        app, attempt, step = await _seed_attempt(db_session, sample_job_data, "tenant-c", "task-c")
        artifact = await visibility_service.record_proof_artifact(
            db_session,
            tenant_id="tenant-c",
            application_id=app.id,
            attempt_id=attempt.id,
            step_id=step.id,
            artifact_type="generated_resume",
            storage_uri="/tmp/persisted-resume.pdf",
            metadata_json={"source": "test"},
        )
        checkpoint = await visibility_service.create_manual_checkpoint(
            db_session,
            tenant_id="tenant-c",
            application_id=app.id,
            attempt_id=attempt.id,
            step_id=step.id,
            checkpoint_type="unsupported_form",
            reason_code="UNSUPPORTED_FORM",
            reason_message="Unsupported form layout detected.",
            blocker_confidence="high",
        )

        list_resp = await client.get(
            f"{API_PREFIX}/manual-checkpoints",
            headers={"X-Tenant-Id": "tenant-c"},
        )
        assert list_resp.status_code == 200
        assert list_resp.json()[0]["reason_code"] == "UNSUPPORTED_FORM"

        detail_resp = await client.get(
            f"{API_PREFIX}/manual-checkpoints/{checkpoint.id}",
            headers={"X-Tenant-Id": "tenant-c"},
        )
        assert detail_resp.status_code == 200
        assert detail_resp.json()["id"] == checkpoint.id

        artifact_list = await client.get(
            f"{API_PREFIX}/proof-artifacts",
            headers={"X-Tenant-Id": "tenant-c"},
        )
        assert artifact_list.status_code == 200
        assert artifact_list.json()[0]["id"] == artifact.id

        artifact_detail = await client.get(
            f"{API_PREFIX}/proof-artifacts/{artifact.id}",
            headers={"X-Tenant-Id": "tenant-c"},
        )
        assert artifact_detail.status_code == 200
        assert artifact_detail.json()["artifact_type"] == "generated_resume"
