"""Unit tests for review queue manual actions."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.domains.applications.workflow import WorkflowService, WorkflowState
from app.models.application import Application
from app.models.job import Job
from app.models.review_task import ReviewTask
from app.schemas.review import ReviewTaskCreate
from app.services import review_queue


async def _create_app_and_workflow(db: AsyncSession, sample_job_data: dict) -> tuple[Application, str]:
    job = Job(**sample_job_data)
    db.add(job)
    await db.flush()
    app = Application(job_id=job.id, status="queued", apply_mode="review", tenant_id="tenant-1")
    db.add(app)
    await db.flush()

    workflow_service = WorkflowService(db)
    run = await workflow_service.create_run(candidate_id=app.id, tenant_id="tenant-1", job_id=job.id)
    await workflow_service.transition_state(
        run.id,
        target_state=WorkflowState.FAILED_MANUAL,
        idempotency_key=f"{app.id}:manual",
        step_name="submit_application",
        error_message="manual needed",
        tenant_id="tenant-1",
    )
    app.workflow_run_id = run.id
    await db.commit()
    return app, run.id


class TestReviewQueue:
    async def test_create_and_apply_retry_action(self, db_session: AsyncSession, sample_job_data: dict):
        app, run_id = await _create_app_and_workflow(db_session, sample_job_data)
        task = await review_queue.create_review_task(
            db_session,
            ReviewTaskCreate(
                tenant_id="tenant-1",
                application_id=app.id,
                workflow_run_id=run_id,
                reason="uncertain_submission",
                idempotency_key=f"{app.id}:review:uncertain",
            ),
        )

        auth = AuthContext(user_id="reviewer-1", tenant_id="tenant-1", role=Role.REVIEWER, enforced=True)
        updated = await review_queue.apply_review_action(
            db_session,
            auth,
            task_id=task.id,
            action="retry",
            notes="retry approved",
        )

        assert updated.status == "resolved"
        refreshed = (await db_session.execute(select(ReviewTask).where(ReviewTask.id == task.id))).scalar_one()
        assert refreshed.resolution_action == "retry"
