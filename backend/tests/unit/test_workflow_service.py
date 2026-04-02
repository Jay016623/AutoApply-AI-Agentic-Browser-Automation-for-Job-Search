"""Unit tests for workflow service orchestration behavior."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.workflow import WorkflowService, WorkflowState, WorkflowTransitionError
from app.models.audit_log import AuditLog
from app.models.workflow_step import WorkflowStep


class TestWorkflowService:
    """Validate idempotency and transition safety at service level."""

    async def test_create_run_defaults(self, db_session: AsyncSession) -> None:
        service = WorkflowService(db_session)
        run = await service.create_run(candidate_id="cand-1", tenant_id="tenant-1", job_id="job-1")

        assert run.current_state == WorkflowState.DISCOVERED
        assert run.status == "active"
        assert run.retry_count == 0

    async def test_transition_is_idempotent_by_key(self, db_session: AsyncSession) -> None:
        service = WorkflowService(db_session)
        run = await service.create_run(candidate_id="cand-1")

        await service.transition_state(
            run_id=run.id,
            target_state=WorkflowState.MATCHED,
            idempotency_key="k1",
            step_name="matching",
        )
        # Replay same idempotency key should no-op (no extra step)
        await service.transition_state(
            run_id=run.id,
            target_state=WorkflowState.MATCHED,
            idempotency_key="k1",
            step_name="matching",
        )

        step_rows = await db_session.execute(
            select(WorkflowStep).where(WorkflowStep.workflow_run_id == run.id)
        )
        assert len(list(step_rows.scalars().all())) == 1

    async def test_invalid_transition_raises(self, db_session: AsyncSession) -> None:
        service = WorkflowService(db_session)
        run = await service.create_run(candidate_id="cand-1")

        with pytest.raises(WorkflowTransitionError):
            await service.transition_state(
                run_id=run.id,
                target_state=WorkflowState.SUBMITTED,
                idempotency_key="invalid-submit",
                step_name="submit",
            )

    async def test_transition_records_audit_event(self, db_session: AsyncSession) -> None:
        service = WorkflowService(db_session)
        run = await service.create_run(candidate_id="cand-1", tenant_id="tenant-1")

        await service.transition_state(
            run_id=run.id,
            target_state=WorkflowState.MATCHED,
            idempotency_key="audit-1",
            step_name="matching",
            actor_id="user-1",
        )

        logs = await db_session.execute(
            select(AuditLog).where(AuditLog.entity_id == run.id)
        )
        audit_rows = list(logs.scalars().all())
        assert len(audit_rows) == 1
        assert audit_rows[0].event_type == "workflow.transition"
