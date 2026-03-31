"""Unit tests for durable application attempt service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.execution import ApplicationAttemptService
from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.audit_log import AuditLog
from app.models.job import Job
from app.models.proof_artifact import ProofArtifact


async def _create_application(db_session: AsyncSession, sample_job_data: dict) -> Application:
    job = Job(**sample_job_data)
    db_session.add(job)
    await db_session.flush()

    app = Application(job_id=job.id, status="queued", apply_mode="review")
    db_session.add(app)
    await db_session.commit()
    return app


class TestApplicationAttemptService:
    async def test_idempotent_attempt_creation(self, db_session: AsyncSession, sample_job_data: dict) -> None:
        app = await _create_application(db_session, sample_job_data)
        service = ApplicationAttemptService(db_session)

        attempt1 = await service.create_or_get_attempt(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id=None,
            candidate_id="cand-1",
            job_id=app.job_id,
            idempotency_key="exec-key-1",
        )
        attempt2 = await service.create_or_get_attempt(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id=None,
            candidate_id="cand-1",
            job_id=app.job_id,
            idempotency_key="exec-key-1",
        )

        assert attempt1.id == attempt2.id

    async def test_step_lifecycle_and_resumability(self, db_session: AsyncSession, sample_job_data: dict) -> None:
        app = await _create_application(db_session, sample_job_data)
        service = ApplicationAttemptService(db_session)
        attempt = await service.create_or_get_attempt(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id="wf-1",
            candidate_id="cand-1",
            job_id=app.job_id,
            idempotency_key="exec-key-2",
        )
        await service.start_attempt(attempt.id)

        step = await service.record_step_started(
            attempt_id=attempt.id,
            step_name="submit",
            sequence_number=1,
            idempotency_key=f"{attempt.id}:submit",
        )
        await service.record_step_completed(step_id=step.id, output_snapshot_json={"ok": True})

        # replay same step key should be idempotent and preserve completed state
        replay = await service.record_step_started(
            attempt_id=attempt.id,
            step_name="submit",
            sequence_number=1,
            idempotency_key=f"{attempt.id}:submit",
        )
        assert replay.id == step.id
        assert replay.status == "completed"

        next_sequence = await service.get_resume_sequence(attempt.id)
        assert next_sequence == 2

    async def test_retry_and_manual_checkpoint_semantics(self, db_session: AsyncSession, sample_job_data: dict) -> None:
        app = await _create_application(db_session, sample_job_data)
        service = ApplicationAttemptService(db_session)
        attempt = await service.create_or_get_attempt(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id="wf-1",
            candidate_id="cand-1",
            job_id=app.job_id,
            idempotency_key="exec-key-3",
        )

        retry_step = await service.record_step_started(
            attempt_id=attempt.id,
            step_name="submit",
            sequence_number=1,
            idempotency_key=f"{attempt.id}:submit-retry",
        )
        await service.record_step_failed(
            step_id=retry_step.id,
            error_code="NETWORK",
            error_message="timeout",
            retryable=True,
        )

        manual_step = await service.record_step_started(
            attempt_id=attempt.id,
            step_name="verify_submission",
            sequence_number=2,
            idempotency_key=f"{attempt.id}:verify",
        )
        await service.record_step_failed(
            step_id=manual_step.id,
            error_code="CAPTCHA",
            error_message="captcha challenge",
            retryable=False,
            manual_checkpoint_reason="captcha detected",
        )

        attempt_row = (await db_session.execute(select(ApplicationAttempt).where(ApplicationAttempt.id == attempt.id))).scalar_one()
        assert attempt_row.status == "waiting_manual"
        assert attempt_row.manual_checkpoint_required is True

        logs = (await db_session.execute(select(AuditLog).where(AuditLog.entity_id == attempt.id))).scalars().all()
        event_types = {row.event_type for row in logs}
        assert "application_attempt_retry_scheduled" in event_types
        assert "application_attempt_waiting_manual" in event_types

    async def test_proof_artifact_linkage(self, db_session: AsyncSession, sample_job_data: dict) -> None:
        app = await _create_application(db_session, sample_job_data)
        service = ApplicationAttemptService(db_session)
        attempt = await service.create_or_get_attempt(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id="wf-1",
            candidate_id="cand-1",
            job_id=app.job_id,
            idempotency_key="exec-key-4",
        )
        step = await service.record_step_started(
            attempt_id=attempt.id,
            step_name="store_proof_artifacts",
            sequence_number=1,
            idempotency_key=f"{attempt.id}:proof",
        )

        artifact = await service.create_proof_artifact(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id="wf-1",
            attempt_id=attempt.id,
            attempt_step_id=step.id,
            artifact_type="screenshot",
            storage_path="s3://bucket/artifact.png",
            metadata_json={"label": "submit-result"},
        )
        assert artifact.attempt_id == attempt.id

        saved = (await db_session.execute(select(ProofArtifact).where(ProofArtifact.id == artifact.id))).scalar_one()
        assert saved.attempt_step_id == step.id

        saved_step = (await db_session.execute(select(ApplicationAttemptStep).where(ApplicationAttemptStep.id == step.id))).scalar_one()
        assert saved_step.id == step.id
