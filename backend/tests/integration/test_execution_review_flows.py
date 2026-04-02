"""Integration-style flow tests for workflow/review/retry behavior."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.domains.applications.workflow import WorkflowService, WorkflowState
from app.models.application import Application
from app.models.job import Job
from app.models.workflow_run import WorkflowRun
from app.schemas.review import ReviewTaskCreate
from app.services import review_queue


async def _seed_app_with_workflow(db: AsyncSession, sample_job_data: dict) -> tuple[Application, WorkflowRun]:
    job = Job(**sample_job_data)
    db.add(job)
    await db.flush()

    app = Application(job_id=job.id, status="queued", apply_mode="review", tenant_id="tenant-1")
    db.add(app)
    await db.flush()

    service = WorkflowService(db)
    run = await service.create_run(candidate_id=app.id, tenant_id="tenant-1", job_id=job.id)
    app.workflow_run_id = run.id
    await db.commit()
    return app, run


class TestExecutionReviewFlows:
    async def test_candidate_match_tailor_review_apply_path(self, db_session: AsyncSession, sample_job_data: dict):
        app, run = await _seed_app_with_workflow(db_session, sample_job_data)
        workflow = WorkflowService(db_session)
        auth = AuthContext(user_id="reviewer-1", tenant_id="tenant-1", role=Role.REVIEWER, enforced=True)

        await workflow.transition_state(run.id, WorkflowState.MATCHED, f"{app.id}:matched", "match", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.SHORTLISTED, f"{app.id}:shortlisted", "shortlist", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.TAILORED, f"{app.id}:tailored", "tailor", tenant_id="tenant-1")
        await workflow.transition_state(
            run.id,
            WorkflowState.FAILED_MANUAL,
            f"{app.id}:manual-review",
            "submit",
            error_message="uncertain submission",
            tenant_id="tenant-1",
        )

        task = await review_queue.create_review_task(
            db_session,
            ReviewTaskCreate(
                tenant_id="tenant-1",
                application_id=app.id,
                workflow_run_id=run.id,
                reason="uncertain_submission",
                idempotency_key=f"{app.id}:review:uncertain",
            ),
        )
        await review_queue.apply_review_action(db_session, auth, task_id=task.id, action="approve", notes="approved")

        refreshed = (await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run.id))).scalar_one()
        assert refreshed.current_state == WorkflowState.READY_TO_APPLY

    async def test_transient_failure_retry_success(self, db_session: AsyncSession, sample_job_data: dict):
        app, run = await _seed_app_with_workflow(db_session, sample_job_data)
        workflow = WorkflowService(db_session)

        await workflow.transition_state(run.id, WorkflowState.MATCHED, f"{app.id}:matched", "match", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.SHORTLISTED, f"{app.id}:shortlisted", "shortlist", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.TAILORED, f"{app.id}:tailored", "tailor", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.READY_TO_APPLY, f"{app.id}:ready", "score", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.APPLYING, f"{app.id}:applying", "submit", tenant_id="tenant-1")
        await workflow.transition_state(
            run.id,
            WorkflowState.FAILED_RETRYABLE,
            f"{app.id}:failed-retryable",
            "submit",
            error_message="timeout",
            tenant_id="tenant-1",
        )
        await workflow.transition_state(run.id, WorkflowState.APPLYING, f"{app.id}:retry-applying", "retry", tenant_id="tenant-1")
        await workflow.transition_state(run.id, WorkflowState.SUBMITTED, f"{app.id}:submitted", "submit", tenant_id="tenant-1")

        refreshed = (await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run.id))).scalar_one()
        assert refreshed.current_state == WorkflowState.SUBMITTED

    async def test_low_confidence_review_approve_continue(self, db_session: AsyncSession, sample_job_data: dict):
        app, run = await _seed_app_with_workflow(db_session, sample_job_data)
        workflow = WorkflowService(db_session)
        auth = AuthContext(user_id="reviewer-2", tenant_id="tenant-1", role=Role.REVIEWER, enforced=True)

        await workflow.transition_state(run.id, WorkflowState.FAILED_MANUAL, f"{app.id}:ats-review", "score", error_message="low confidence", tenant_id="tenant-1")
        task = await review_queue.create_review_task(
            db_session,
            ReviewTaskCreate(
                tenant_id="tenant-1",
                application_id=app.id,
                workflow_run_id=run.id,
                reason="low_confidence_match",
                details_json={"ats_score": 0.42},
                idempotency_key=f"{app.id}:review:low-confidence",
            ),
        )

        resolved = await review_queue.apply_review_action(db_session, auth, task_id=task.id, action="approve", notes="override")
        assert resolved.status == "resolved"

        refreshed = (await db_session.execute(select(WorkflowRun).where(WorkflowRun.id == run.id))).scalar_one()
        assert refreshed.current_state == WorkflowState.READY_TO_APPLY
