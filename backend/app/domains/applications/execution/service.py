"""Durable execution service for application attempts."""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.proof_artifact import ProofArtifact
from app.services.audit import AuditLogCreate, record_audit_log

ATTEMPT_TERMINAL_STATES = {"completed", "failed_manual", "abandoned"}


class ApplicationAttemptService:
    """Persistence-focused service for resumable apply execution."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_or_get_attempt(
        self,
        *,
        tenant_id: str | None,
        application_id: str,
        workflow_run_id: str | None,
        candidate_id: str | None,
        job_id: str | None,
        idempotency_key: str,
    ) -> ApplicationAttempt:
        result = await self._db.execute(
            select(ApplicationAttempt).where(
                ApplicationAttempt.application_id == application_id,
                ApplicationAttempt.idempotency_key == idempotency_key,
            ),
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            return existing

        max_result = await self._db.execute(
            select(func.max(ApplicationAttempt.attempt_number)).where(
                ApplicationAttempt.application_id == application_id,
            ),
        )
        max_attempt_number = max_result.scalar_one_or_none() or 0

        attempt = ApplicationAttempt(
            tenant_id=tenant_id,
            application_id=application_id,
            workflow_run_id=workflow_run_id,
            candidate_id=candidate_id,
            job_id=job_id,
            status="pending",
            current_step=None,
            idempotency_key=idempotency_key,
            attempt_number=max_attempt_number + 1,
        )
        self._db.add(attempt)
        await self._db.commit()
        await self._db.refresh(attempt)

        await self._audit(
            attempt,
            "application_attempt_created",
            message="Execution attempt created",
        )
        return attempt

    async def start_attempt(self, attempt_id: str) -> ApplicationAttempt:
        attempt = await self._get_attempt(attempt_id)
        if attempt.status != "running":
            attempt.status = "running"
            attempt.started_at = attempt.started_at or datetime.now(UTC)
            await self._db.commit()
            await self._db.refresh(attempt)
            await self._audit(attempt, "application_attempt_started", message="Execution started")
        return attempt

    async def record_step_started(
        self,
        *,
        attempt_id: str,
        step_name: str,
        sequence_number: int,
        idempotency_key: str,
        input_snapshot_json: dict[str, Any] | None = None,
    ) -> ApplicationAttemptStep:
        existing = await self._get_step_by_key(attempt_id, idempotency_key)
        if existing is not None:
            return existing

        step = ApplicationAttemptStep(
            tenant_id=(await self._get_attempt(attempt_id)).tenant_id,
            attempt_id=attempt_id,
            step_name=step_name,
            sequence_number=sequence_number,
            status="running",
            started_at=datetime.now(UTC),
            idempotency_key=idempotency_key,
            input_snapshot_json=input_snapshot_json,
        )
        self._db.add(step)

        attempt = await self._get_attempt(attempt_id)
        attempt.current_step = step_name
        attempt.status = "running"

        await self._db.commit()
        await self._db.refresh(step)
        await self._audit(
            attempt,
            "application_attempt_step_started",
            message=f"Step started: {step_name}",
            metadata={"sequence_number": sequence_number, "step_id": step.id},
        )
        return step

    async def record_step_completed(
        self,
        *,
        step_id: str,
        output_snapshot_json: dict[str, Any] | None = None,
    ) -> ApplicationAttemptStep:
        step = await self._get_step(step_id)
        step.status = "completed"
        step.completed_at = datetime.now(UTC)
        step.output_snapshot_json = output_snapshot_json
        await self._db.commit()
        await self._db.refresh(step)

        attempt = await self._get_attempt(step.attempt_id)
        await self._audit(
            attempt,
            "application_attempt_step_completed",
            message=f"Step completed: {step.step_name}",
            metadata={"step_id": step.id, "step_name": step.step_name},
        )
        return step

    async def record_step_failed(
        self,
        *,
        step_id: str,
        error_code: str,
        error_message: str,
        retryable: bool,
        manual_checkpoint_reason: str | None = None,
    ) -> ApplicationAttemptStep:
        step = await self._get_step(step_id)
        step.status = "failed_retryable" if retryable else "failed_manual"
        step.retryable = retryable
        step.retry_count = step.retry_count + (1 if retryable else 0)
        step.error_code = error_code
        step.error_message = error_message
        step.completed_at = datetime.now(UTC)

        attempt = await self._get_attempt(step.attempt_id)
        attempt.last_error_code = error_code
        attempt.last_error_message = error_message
        if manual_checkpoint_reason:
            attempt.status = "waiting_manual"
            attempt.manual_checkpoint_required = True
            attempt.manual_checkpoint_reason = manual_checkpoint_reason
        else:
            attempt.status = "failed_retryable" if retryable else "failed_manual"
        await self._db.commit()
        await self._db.refresh(step)

        await self._audit(
            attempt,
            "application_attempt_step_failed",
            message=f"Step failed: {step.step_name}",
            metadata={"step_id": step.id, "error_code": error_code, "retryable": retryable},
        )

        if manual_checkpoint_reason:
            await self._audit(
                attempt,
                "application_attempt_waiting_manual",
                message=manual_checkpoint_reason,
            )
        elif retryable:
            await self._audit(
                attempt,
                "application_attempt_retry_scheduled",
                message=f"Retry scheduled from step {step.step_name}",
            )
        return step

    async def complete_attempt(self, attempt_id: str) -> ApplicationAttempt:
        attempt = await self._get_attempt(attempt_id)
        attempt.status = "completed"
        attempt.completed_at = datetime.now(UTC)
        await self._db.commit()
        await self._db.refresh(attempt)
        await self._audit(attempt, "application_attempt_completed", message="Execution completed")
        return attempt

    async def abandon_attempt(self, attempt_id: str, reason: str) -> ApplicationAttempt:
        attempt = await self._get_attempt(attempt_id)
        attempt.status = "abandoned"
        attempt.last_error_message = reason
        attempt.completed_at = datetime.now(UTC)
        await self._db.commit()
        await self._db.refresh(attempt)
        await self._audit(attempt, "application_attempt_abandoned", message=reason)
        return attempt

    async def create_proof_artifact(
        self,
        *,
        tenant_id: str | None,
        application_id: str | None,
        workflow_run_id: str | None,
        attempt_id: str | None,
        attempt_step_id: str | None,
        artifact_type: str,
        storage_path: str,
        checksum: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> ProofArtifact:
        artifact = ProofArtifact(
            tenant_id=tenant_id,
            application_id=application_id,
            workflow_run_id=workflow_run_id,
            attempt_id=attempt_id,
            attempt_step_id=attempt_step_id,
            artifact_type=artifact_type,
            storage_path=storage_path,
            checksum=checksum,
            metadata_json=metadata_json,
        )
        self._db.add(artifact)
        await self._db.commit()
        await self._db.refresh(artifact)
        return artifact

    async def get_resume_sequence(self, attempt_id: str) -> int:
        result = await self._db.execute(
            select(func.max(ApplicationAttemptStep.sequence_number)).where(
                ApplicationAttemptStep.attempt_id == attempt_id,
                ApplicationAttemptStep.status == "completed",
            ),
        )
        return (result.scalar_one_or_none() or 0) + 1

    async def _get_attempt(self, attempt_id: str) -> ApplicationAttempt:
        result = await self._db.execute(select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id))
        return result.scalar_one()

    async def _get_step(self, step_id: str) -> ApplicationAttemptStep:
        result = await self._db.execute(select(ApplicationAttemptStep).where(ApplicationAttemptStep.id == step_id))
        return result.scalar_one()

    async def _get_step_by_key(self, attempt_id: str, idempotency_key: str) -> ApplicationAttemptStep | None:
        result = await self._db.execute(
            select(ApplicationAttemptStep).where(
                ApplicationAttemptStep.attempt_id == attempt_id,
                ApplicationAttemptStep.idempotency_key == idempotency_key,
            ),
        )
        return result.scalar_one_or_none()

    async def _audit(
        self,
        attempt: ApplicationAttempt,
        event_type: str,
        message: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await record_audit_log(
            self._db,
            AuditLogCreate(
                tenant_id=attempt.tenant_id,
                actor_id=None,
                actor_type="system",
                entity_type="application_attempt",
                entity_id=attempt.id,
                event_type=event_type,
                status=attempt.status,
                message=message,
                event_metadata=metadata,
            ),
        )
