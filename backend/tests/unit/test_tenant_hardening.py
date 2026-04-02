"""Tests for strict tenant backfill and validation helpers."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.job import Job
from app.models.proof_artifact import ProofArtifact
from app.models.review_task import ReviewTask
from app.models.workflow_run import WorkflowRun
from app.services import tenant_hardening


class TestTenantHardening:
    async def test_safe_backfill_populates_critical_entities(self, db_session: AsyncSession, sample_job_data: dict):
        job = Job(**sample_job_data)
        db_session.add(job)
        await db_session.flush()

        app = Application(job_id=job.id, status="queued", apply_mode="review", tenant_id="tenant-1")
        db_session.add(app)
        await db_session.flush()

        run = WorkflowRun(candidate_id=app.id, tenant_id=None, job_id=job.id, current_state="discovered", status="active")
        db_session.add(run)
        await db_session.flush()
        app.workflow_run_id = run.id

        attempt = ApplicationAttempt(
            tenant_id=None,
            application_id=app.id,
            workflow_run_id=run.id,
            status="running",
            idempotency_key=f"idem-{app.id}",
            attempt_number=1,
        )
        db_session.add(attempt)
        await db_session.flush()

        artifact = ProofArtifact(
            tenant_id=None,
            application_id=app.id,
            workflow_run_id=run.id,
            attempt_id=attempt.id,
            artifact_type="trace",
            storage_path="attempt://trace",
            storage_backend="local",
        )
        db_session.add(artifact)

        review = ReviewTask(
            tenant_id=None,
            application_id=app.id,
            workflow_run_id=run.id,
            reason="uncertain_submission",
            status="open",
            idempotency_key=f"review-{app.id}",
        )
        db_session.add(review)
        await db_session.commit()

        report = await tenant_hardening.run_safe_tenant_backfill(db_session)
        assert report.applications_updated >= 0

        counts = await tenant_hardening.strict_tenant_null_counts(db_session)
        assert counts["applications"] == 0
        assert counts["workflow_runs"] == 0
        assert counts["application_attempts"] == 0
        assert counts["proof_artifacts"] == 0
        assert counts["review_tasks"] == 0
