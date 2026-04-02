"""Operational timeline query service for execution and audit visibility."""

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role, ensure_role, require_tenant
from app.core.exceptions import RecordNotFoundError
from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.audit_log import AuditLog
from app.models.proof_artifact import ProofArtifact
from app.models.review_task import ReviewTask
from app.models.workflow_step import WorkflowStep
from app.schemas.execution import TimelineEventResponse, TimelineResponse

_READ_ROLES = {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.RECRUITER, Role.REVIEWER, Role.READ_ONLY}
_SENSITIVE_KEYS = {"token", "access_token", "secret", "password", "authorization", "email", "phone"}


def _safe_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    result: dict[str, Any] = {}
    for key, value in payload.items():
        lk = key.lower()
        if any(token in lk for token in _SENSITIVE_KEYS):
            result[key] = "[redacted]"
            continue
        if isinstance(value, str) and len(value) > 200:
            result[key] = value[:200] + "..."
        else:
            result[key] = value
    return result


def _tenant_clause(auth: AuthContext, column):
    if auth.enforced:
        return column == require_tenant(auth)
    if auth.tenant_id:
        return column == auth.tenant_id
    return None


async def _resolve_context(
    db: AsyncSession,
    auth: AuthContext,
    *,
    application_id: str | None,
    workflow_run_id: str | None,
    attempt_id: str | None,
) -> tuple[str | None, str | None, list[str]]:
    tenant_scope = require_tenant(auth) if auth.enforced else auth.tenant_id
    app_id = application_id
    run_id = workflow_run_id
    attempt_ids: list[str] = []

    if attempt_id:
        attempt = (await db.execute(select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id))).scalar_one_or_none()
        if attempt is None:
            raise RecordNotFoundError("ApplicationAttempt", attempt_id)
        if tenant_scope and attempt.tenant_id != tenant_scope:
            raise RecordNotFoundError("ApplicationAttempt", attempt_id)
        app_id = app_id or attempt.application_id
        run_id = run_id or attempt.workflow_run_id
        attempt_ids.append(attempt.id)

    if app_id:
        app = (await db.execute(select(Application).where(Application.id == app_id))).scalar_one_or_none()
        if app is None:
            raise RecordNotFoundError("Application", app_id)
        if tenant_scope and app.tenant_id != tenant_scope:
            raise RecordNotFoundError("Application", app_id)
        run_id = run_id or app.workflow_run_id

    if run_id and not app_id:
        app = (await db.execute(select(Application).where(Application.workflow_run_id == run_id))).scalar_one_or_none()
        if app is not None:
            if tenant_scope and app.tenant_id != tenant_scope:
                raise RecordNotFoundError("WorkflowRun", run_id)
            app_id = app.id

    if app_id and not attempt_ids:
        query = select(ApplicationAttempt.id).where(ApplicationAttempt.application_id == app_id)
        if tenant_scope:
            query = query.where(ApplicationAttempt.tenant_id == tenant_scope)
        attempt_ids = [row[0] for row in (await db.execute(query)).all()]

    return app_id, run_id, attempt_ids


async def execution_timeline(
    db: AsyncSession,
    auth: AuthContext,
    *,
    application_id: str | None,
    workflow_run_id: str | None,
    attempt_id: str | None,
) -> TimelineResponse:
    ensure_role(auth, _READ_ROLES)
    app_id, run_id, attempt_ids = await _resolve_context(
        db,
        auth,
        application_id=application_id,
        workflow_run_id=workflow_run_id,
        attempt_id=attempt_id,
    )

    events: list[TimelineEventResponse] = []

    if run_id:
        query = select(WorkflowStep).where(WorkflowStep.workflow_run_id == run_id)
        for step in (await db.execute(query)).scalars().all():
            events.append(
                TimelineEventResponse(
                    event_id=f"workflow-step:{step.id}",
                    category="workflow_transition",
                    event_type=step.step_name,
                    occurred_at=step.created_at,
                    tenant_id=auth.tenant_id,
                    application_id=app_id,
                    workflow_run_id=run_id,
                    trace_id=step.idempotency_key,
                    state_from=step.from_state,
                    state_to=step.to_state,
                    status=step.status,
                    message=step.error_message,
                    payload={"retryable": step.retryable, "attempt_number": step.attempt_number},
                ),
            )

    if attempt_ids:
        steps_query = select(ApplicationAttemptStep).where(ApplicationAttemptStep.attempt_id.in_(attempt_ids))
        for step in (await db.execute(steps_query)).scalars().all():
            category = "retry_event" if step.retry_count > 0 else "attempt_step"
            events.append(
                TimelineEventResponse(
                    event_id=f"attempt-step:{step.id}",
                    category=category,
                    event_type=step.step_name,
                    occurred_at=step.completed_at or step.started_at or step.created_at,
                    tenant_id=step.tenant_id,
                    application_id=app_id,
                    workflow_run_id=run_id,
                    attempt_id=step.attempt_id,
                    trace_id=step.idempotency_key,
                    status=step.status,
                    failure_classification=step.error_code,
                    message=step.error_message,
                    payload=_safe_payload(step.output_snapshot_json if isinstance(step.output_snapshot_json, dict) else None),
                ),
            )

        artifact_query = select(ProofArtifact).where(ProofArtifact.attempt_id.in_(attempt_ids))
        for artifact in (await db.execute(artifact_query)).scalars().all():
            events.append(
                TimelineEventResponse(
                    event_id=f"artifact:{artifact.id}",
                    category="artifact_created",
                    event_type=artifact.artifact_type,
                    occurred_at=artifact.created_at,
                    tenant_id=artifact.tenant_id,
                    application_id=artifact.application_id,
                    workflow_run_id=artifact.workflow_run_id,
                    attempt_id=artifact.attempt_id,
                    artifact_id=artifact.id,
                    artifact_type=artifact.artifact_type,
                    status="stored",
                    payload={
                        "storage_backend": artifact.storage_backend,
                        "size_bytes": artifact.size_bytes,
                        "content_type": artifact.content_type,
                    },
                ),
            )

    review_query = select(ReviewTask)
    if run_id:
        review_query = review_query.where(ReviewTask.workflow_run_id == run_id)
    elif app_id:
        review_query = review_query.where(ReviewTask.application_id == app_id)
    else:
        review_query = review_query.where(ReviewTask.id == "")
    tenant_filter = _tenant_clause(auth, ReviewTask.tenant_id)
    if tenant_filter is not None:
        review_query = review_query.where(tenant_filter)
    for task in (await db.execute(review_query)).scalars().all():
        events.append(
            TimelineEventResponse(
                event_id=f"review:{task.id}",
                category="review_action",
                event_type=task.reason,
                occurred_at=task.resolved_at or task.created_at,
                tenant_id=task.tenant_id,
                application_id=task.application_id,
                workflow_run_id=task.workflow_run_id,
                attempt_id=task.attempt_id,
                actor_id=task.resolved_by,
                status=task.status,
                failure_classification=task.reason,
                message=task.resolution_notes,
                payload=_safe_payload(task.details_json if isinstance(task.details_json, dict) else None),
            ),
        )

    events.sort(key=lambda event: event.occurred_at)
    return TimelineResponse(items=events)


async def audit_timeline(
    db: AsyncSession,
    auth: AuthContext,
    *,
    application_id: str | None,
    workflow_run_id: str | None,
    attempt_id: str | None,
    limit: int = 200,
) -> TimelineResponse:
    ensure_role(auth, _READ_ROLES)
    app_id, run_id, attempt_ids = await _resolve_context(
        db,
        auth,
        application_id=application_id,
        workflow_run_id=workflow_run_id,
        attempt_id=attempt_id,
    )

    query = select(AuditLog).order_by(AuditLog.created_at.asc()).limit(limit)
    tenant_filter = _tenant_clause(auth, AuditLog.tenant_id)
    if tenant_filter is not None:
        query = query.where(tenant_filter)

    candidate_entity_ids = {eid for eid in [app_id, run_id, *attempt_ids] if eid}
    rows = (await db.execute(query)).scalars().all()

    events: list[TimelineEventResponse] = []
    for row in rows:
        metadata = row.event_metadata if isinstance(row.event_metadata, dict) else {}
        if candidate_entity_ids and row.entity_id not in candidate_entity_ids and metadata.get("application_id") not in candidate_entity_ids:
            continue
        events.append(
            TimelineEventResponse(
                event_id=f"audit:{row.id}",
                category="audit_event",
                event_type=row.event_type,
                occurred_at=row.created_at,
                tenant_id=row.tenant_id,
                application_id=metadata.get("application_id") if isinstance(metadata, dict) else app_id,
                workflow_run_id=run_id if row.entity_type == "workflow_run" else metadata.get("workflow_run_id"),
                attempt_id=row.entity_id if row.entity_type == "application_attempt" else metadata.get("attempt_id"),
                trace_id=metadata.get("idempotency_key") if isinstance(metadata, dict) else None,
                actor_id=row.actor_id,
                actor_type=row.actor_type,
                status=row.status,
                message=row.message,
                payload=_safe_payload(metadata),
            ),
        )

    events.sort(key=lambda event: event.occurred_at)
    return TimelineResponse(items=events)
