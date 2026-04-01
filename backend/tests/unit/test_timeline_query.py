"""Unit tests for execution/audit timeline query surfaces."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.domains.applications.execution import ApplicationAttemptService
from app.domains.applications.workflow import WorkflowService, WorkflowState
from app.models.application import Application
from app.models.job import Job
from app.schemas.review import ReviewTaskCreate
from app.services import review_queue, timeline_query


async def _seed_context(db: AsyncSession, sample_job_data: dict) -> tuple[str, str, str]:
    job = Job(**sample_job_data)
    db.add(job)
    await db.flush()
    app = Application(job_id=job.id, status="queued", apply_mode="review", tenant_id="tenant-1")
    db.add(app)
    await db.flush()

    workflow = WorkflowService(db)
    run = await workflow.create_run(candidate_id=app.id, tenant_id="tenant-1", job_id=job.id)
    app.workflow_run_id = run.id
    await workflow.transition_state(
        run.id,
        target_state=WorkflowState.MATCHED,
        idempotency_key=f"{app.id}:matched",
        step_name="match",
        tenant_id="tenant-1",
    )

    attempts = ApplicationAttemptService(db, tenant_scope="tenant-1")
    attempt = await attempts.create_or_get_attempt(
        tenant_id="tenant-1",
        application_id=app.id,
        workflow_run_id=run.id,
        candidate_id=app.id,
        job_id=job.id,
        idempotency_key=f"{app.id}:attempt",
    )
    step = await attempts.record_step_started(
        attempt_id=attempt.id,
        step_name="submit",
        sequence_number=1,
        idempotency_key=f"{attempt.id}:submit",
    )
    await attempts.record_step_failed(
        step_id=step.id,
        error_code="CAPTCHA",
        error_message="captcha challenge",
        retryable=False,
        manual_checkpoint_reason="captcha required",
    )

    await review_queue.create_review_task(
        db,
        ReviewTaskCreate(
            tenant_id="tenant-1",
            application_id=app.id,
            workflow_run_id=run.id,
            attempt_id=attempt.id,
            reason="captcha_or_auth_block",
            idempotency_key=f"{app.id}:review:captcha",
        ),
    )
    return app.id, run.id, attempt.id


class TestTimelineQuery:
    async def test_execution_and_audit_timeline(self, db_session: AsyncSession, sample_job_data: dict):
        app_id, run_id, attempt_id = await _seed_context(db_session, sample_job_data)
        auth = AuthContext(user_id="operator-1", tenant_id="tenant-1", role=Role.OPERATOR, enforced=True)

        exec_timeline = await timeline_query.execution_timeline(
            db_session,
            auth,
            application_id=app_id,
            workflow_run_id=run_id,
            attempt_id=attempt_id,
        )
        categories = {event.category for event in exec_timeline.items}
        assert "workflow_transition" in categories
        assert "attempt_step" in categories or "retry_event" in categories
        assert "review_action" in categories

        audit_timeline = await timeline_query.audit_timeline(
            db_session,
            auth,
            application_id=app_id,
            workflow_run_id=run_id,
            attempt_id=attempt_id,
            limit=100,
        )
        assert len(audit_timeline.items) >= 1
