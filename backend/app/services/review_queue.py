"""Tenant-scoped review queue service for manual oversight."""

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, ApplicationStatus
from app.core.auth import AuthContext, Role, ensure_role, ensure_tenant_access, require_tenant
from app.core.exceptions import RecordNotFoundError
from app.domains.applications.workflow import WorkflowService, WorkflowState
from app.models.application import Application
from app.models.review_task import ReviewTask
from app.schemas.review import ReviewTaskCreate, ReviewTaskListResponse, ReviewTaskResponse
from app.services.audit import AuditLogCreate, record_audit_log

_REVIEW_ROLES = {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.REVIEWER}
_ALLOWED_ACTIONS = {"approve", "reject", "retry", "mark_manual_complete", "abandon"}
_ALLOWED_REASONS = {
    "low_confidence_match",
    "risky_tailoring",
    "incomplete_answers",
    "captcha_or_auth_block",
    "uncertain_submission",
    "duplicate_risk",
    "unsupported_ui",
}


async def create_review_task(db: AsyncSession, payload: ReviewTaskCreate) -> ReviewTask:
    if payload.reason not in _ALLOWED_REASONS:
        raise ValueError("unsupported_review_reason")

    existing = (
        await db.execute(
            select(ReviewTask).where(
                ReviewTask.workflow_run_id == payload.workflow_run_id,
                ReviewTask.idempotency_key == payload.idempotency_key,
            ),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    task = ReviewTask(
        tenant_id=payload.tenant_id,
        application_id=payload.application_id,
        workflow_run_id=payload.workflow_run_id,
        attempt_id=payload.attempt_id,
        reason=payload.reason,
        status="open",
        risk_level=payload.risk_level,
        details_json=payload.details_json,
        idempotency_key=payload.idempotency_key,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    await record_audit_log(
        db,
        AuditLogCreate(
            tenant_id=task.tenant_id,
            actor_id=None,
            actor_type="system",
            entity_type="review_task",
            entity_id=task.id,
            event_type="review.task.created",
            status="open",
            message=f"Review task created for reason={task.reason}",
            event_metadata={"workflow_run_id": task.workflow_run_id, "application_id": task.application_id},
        ),
    )
    return task


async def list_review_tasks(
    db: AsyncSession,
    auth: AuthContext,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    status: str | None = None,
    reason: str | None = None,
) -> ReviewTaskListResponse:
    ensure_role(auth, _REVIEW_ROLES)
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    query = select(ReviewTask)
    count_query = select(func.count(ReviewTask.id))

    if auth.enforced:
        tenant_id = require_tenant(auth)
        query = query.where(ReviewTask.tenant_id == tenant_id)
        count_query = count_query.where(ReviewTask.tenant_id == tenant_id)
    elif auth.tenant_id:
        query = query.where(ReviewTask.tenant_id == auth.tenant_id)
        count_query = count_query.where(ReviewTask.tenant_id == auth.tenant_id)

    if status:
        query = query.where(ReviewTask.status == status)
        count_query = count_query.where(ReviewTask.status == status)
    if reason:
        query = query.where(ReviewTask.reason == reason)
        count_query = count_query.where(ReviewTask.reason == reason)

    rows = list((await db.execute(query.order_by(ReviewTask.created_at.desc()).offset(offset).limit(page_size))).scalars().all())
    total = int((await db.execute(count_query)).scalar() or 0)
    return ReviewTaskListResponse(
        items=[ReviewTaskResponse.model_validate(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


async def get_review_task(db: AsyncSession, auth: AuthContext, task_id: str) -> ReviewTask:
    ensure_role(auth, _REVIEW_ROLES)
    task = (await db.execute(select(ReviewTask).where(ReviewTask.id == task_id))).scalar_one_or_none()
    if task is None:
        raise RecordNotFoundError("ReviewTask", task_id)
    ensure_tenant_access(auth, task.tenant_id)
    return task


async def apply_review_action(
    db: AsyncSession,
    auth: AuthContext,
    *,
    task_id: str,
    action: str,
    notes: str | None,
) -> ReviewTask:
    ensure_role(auth, _REVIEW_ROLES)
    if action not in _ALLOWED_ACTIONS:
        raise ValueError("unsupported_review_action")

    task = await get_review_task(db, auth, task_id)
    if task.status in {"resolved", "rejected", "abandoned"}:
        return task

    workflow_service = WorkflowService(db)
    target_state: WorkflowState | None = None
    task_status = "resolved"

    if action in {"approve", "retry"}:
        target_state = WorkflowState.READY_TO_APPLY
    elif action == "mark_manual_complete":
        target_state = WorkflowState.SUBMITTED
    elif action == "reject":
        target_state = WorkflowState.FAILED_MANUAL
        task_status = "rejected"
    elif action == "abandon":
        target_state = WorkflowState.ABANDONED
        task_status = "abandoned"

    if target_state is not None:
        await workflow_service.transition_state(
            task.workflow_run_id,
            target_state=target_state,
            idempotency_key=f"review:{task.id}:{action}",
            step_name="review_action",
            actor_id=auth.user_id,
            error_message=notes,
            tenant_id=task.tenant_id,
        )

    if task.application_id and action in {"approve", "retry"}:
        app = (await db.execute(select(Application).where(Application.id == task.application_id))).scalar_one_or_none()
        if app is not None:
            app.status = ApplicationStatus.APPROVED
    if task.application_id and action in {"reject", "abandon"}:
        app = (await db.execute(select(Application).where(Application.id == task.application_id))).scalar_one_or_none()
        if app is not None:
            app.status = ApplicationStatus.FAILED
            app.notes = notes or f"review_action:{action}"

    task.status = task_status
    task.resolution_action = action
    task.resolution_notes = notes
    task.resolved_by = auth.user_id
    task.resolved_at = datetime.now(UTC)

    await db.commit()
    await db.refresh(task)

    await record_audit_log(
        db,
        AuditLogCreate(
            tenant_id=task.tenant_id,
            actor_id=auth.user_id,
            actor_type="user",
            entity_type="review_task",
            entity_id=task.id,
            event_type="review.task.action",
            status=task.status,
            message=f"action={action}",
            event_metadata={"notes": notes, "workflow_run_id": task.workflow_run_id, "application_id": task.application_id},
        ),
    )
    return task
