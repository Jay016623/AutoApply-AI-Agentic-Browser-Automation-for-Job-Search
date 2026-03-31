"""Workflow integration points for workers.

Workers can call these helpers as they progressively adopt workflow-run
execution while keeping current business behavior intact.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.applications.workflow import WorkflowService, WorkflowState


async def mark_discovered(
    db: AsyncSession,
    run_id: str,
    idempotency_key: str,
) -> None:
    service = WorkflowService(db)
    await service.transition_state(
        run_id=run_id,
        target_state=WorkflowState.DISCOVERED,
        idempotency_key=idempotency_key,
        step_name="discovery",
    )


async def mark_matched(
    db: AsyncSession,
    run_id: str,
    idempotency_key: str,
) -> None:
    service = WorkflowService(db)
    await service.transition_state(
        run_id=run_id,
        target_state=WorkflowState.MATCHED,
        idempotency_key=idempotency_key,
        step_name="matching",
    )
