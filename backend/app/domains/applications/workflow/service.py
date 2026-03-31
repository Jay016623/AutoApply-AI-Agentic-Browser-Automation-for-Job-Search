"""Workflow orchestration service for durable transitions."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.models.workflow_run import WorkflowRun
from app.models.workflow_step import WorkflowStep
from app.services.audit import AuditLogCreate, record_audit_log

from .retry_policy import RetryDecision, evaluate_retry
from .states import WorkflowState, transition


class WorkflowTransitionError(ValueError):
    """Raised when an invalid transition is requested."""


class WorkflowService:
    """Durable workflow service with idempotent transitions."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create_run(
        self,
        candidate_id: str,
        tenant_id: str | None = None,
        job_id: str | None = None,
        max_retries: int = 3,
    ) -> WorkflowRun:
        """Create a new workflow run initialized at DISCOVERED."""
        run = WorkflowRun(
            tenant_id=tenant_id,
            candidate_id=candidate_id,
            job_id=job_id,
            current_state=WorkflowState.DISCOVERED,
            status="active",
            retry_count=0,
            max_retries=max_retries,
        )
        self._db.add(run)
        await self._db.commit()
        await self._db.refresh(run)
        return run

    async def get_run(self, run_id: str) -> WorkflowRun:
        """Load a workflow run or raise not found."""
        result = await self._db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise RecordNotFoundError("WorkflowRun", run_id)
        return run

    async def transition_state(
        self,
        run_id: str,
        target_state: WorkflowState,
        idempotency_key: str,
        step_name: str,
        actor_id: str | None = None,
        error_message: str | None = None,
    ) -> WorkflowRun:
        """Perform idempotent state transition and audit it."""
        run = await self.get_run(run_id)

        existing = await self._find_step_by_idempotency(run_id, idempotency_key)
        if existing is not None:
            # Idempotent replay: return current persisted run unchanged.
            return run

        current = WorkflowState(run.current_state)
        validation = transition(current, target_state)
        if not validation.allowed:
            raise WorkflowTransitionError(
                f"Cannot transition from {current} to {target_state}: {validation.reason}",
            )

        attempt_number = run.retry_count + 1
        retryable = target_state == WorkflowState.FAILED_RETRYABLE

        step = WorkflowStep(
            workflow_run_id=run.id,
            step_name=step_name,
            from_state=current,
            to_state=target_state,
            status="completed" if not retryable else "failed",
            retryable=retryable,
            attempt_number=attempt_number,
            idempotency_key=idempotency_key,
            error_message=error_message,
        )
        self._db.add(step)

        run.current_state = target_state
        run.last_error = error_message
        if retryable:
            run.retry_count = run.retry_count + 1

        if target_state in (WorkflowState.SUBMITTED, WorkflowState.ABANDONED, WorkflowState.FAILED_MANUAL):
            run.status = "completed"
            run.completed_at = datetime.now(UTC)

        await self._db.commit()
        await self._db.refresh(run)

        await record_audit_log(
            self._db,
            AuditLogCreate(
                tenant_id=run.tenant_id,
                actor_id=actor_id,
                actor_type="system" if actor_id is None else "user",
                entity_type="workflow_run",
                entity_id=run.id,
                event_type="workflow.transition",
                status="completed" if validation.allowed else "rejected",
                message=f"{current} -> {target_state}",
                event_metadata={
                    "step_name": step_name,
                    "idempotency_key": idempotency_key,
                    "retry_count": run.retry_count,
                    "error_message": error_message,
                },
            ),
        )
        return run

    async def evaluate_retry(self, run_id: str) -> RetryDecision:
        """Evaluate retry policy for a workflow run."""
        run = await self.get_run(run_id)
        return evaluate_retry(
            state=WorkflowState(run.current_state),
            retry_count=run.retry_count,
            max_retries=run.max_retries,
        )

    async def _find_step_by_idempotency(
        self,
        run_id: str,
        idempotency_key: str,
    ) -> WorkflowStep | None:
        result = await self._db.execute(
            select(WorkflowStep).where(
                WorkflowStep.workflow_run_id == run_id,
                WorkflowStep.idempotency_key == idempotency_key,
            ),
        )
        return result.scalar_one_or_none()
