"""Strict-mode tenant hardening checks and phased backfill helpers."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.application_attempt import ApplicationAttempt
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.proof_artifact import ProofArtifact
from app.models.review_task import ReviewTask
from app.models.workflow_run import WorkflowRun


@dataclass(frozen=True)
class BackfillReport:
    jobs_updated: int = 0
    applications_updated: int = 0
    workflow_runs_updated: int = 0
    attempts_updated: int = 0
    artifacts_updated: int = 0
    review_tasks_updated: int = 0


async def run_safe_tenant_backfill(db: AsyncSession) -> BackfillReport:
    """Backfill tenant ownership only when source ownership is deterministic."""

    jobs_updated = (
        await db.execute(
            update(Job)
            .where(Job.tenant_id.is_(None))
            .where(
                Job.id.in_(
                    select(Application.job_id).where(Application.tenant_id.is_not(None)),
                ),
            )
            .values(
                tenant_id=(
                    select(Application.tenant_id)
                    .where(Application.job_id == Job.id, Application.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    applications_updated = (
        await db.execute(
            update(Application)
            .where(Application.tenant_id.is_(None))
            .values(
                tenant_id=(
                    select(Job.tenant_id)
                    .where(Job.id == Application.job_id, Job.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    workflow_runs_updated = (
        await db.execute(
            update(WorkflowRun)
            .where(WorkflowRun.tenant_id.is_(None))
            .values(
                tenant_id=(
                    select(Application.tenant_id)
                    .where(Application.workflow_run_id == WorkflowRun.id, Application.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    attempts_updated = (
        await db.execute(
            update(ApplicationAttempt)
            .where(ApplicationAttempt.tenant_id.is_(None))
            .values(
                tenant_id=(
                    select(Application.tenant_id)
                    .where(Application.id == ApplicationAttempt.application_id, Application.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    artifacts_updated = (
        await db.execute(
            update(ProofArtifact)
            .where(ProofArtifact.tenant_id.is_(None))
            .values(
                tenant_id=(
                    select(ApplicationAttempt.tenant_id)
                    .where(ApplicationAttempt.id == ProofArtifact.attempt_id, ApplicationAttempt.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    review_tasks_updated = (
        await db.execute(
            update(ReviewTask)
            .where(ReviewTask.tenant_id.is_(None))
            .values(
                tenant_id=(
                    select(WorkflowRun.tenant_id)
                    .where(WorkflowRun.id == ReviewTask.workflow_run_id, WorkflowRun.tenant_id.is_not(None))
                    .limit(1)
                    .scalar_subquery()
                ),
            ),
        )
    ).rowcount or 0

    await db.commit()
    return BackfillReport(
        jobs_updated=jobs_updated,
        applications_updated=applications_updated,
        workflow_runs_updated=workflow_runs_updated,
        attempts_updated=attempts_updated,
        artifacts_updated=artifacts_updated,
        review_tasks_updated=review_tasks_updated,
    )


async def strict_tenant_null_counts(db: AsyncSession) -> dict[str, int]:
    """Return null tenant ownership counts for strict-mode critical entities."""

    tables = {
        "jobs": Job,
        "applications": Application,
        "workflow_runs": WorkflowRun,
        "application_attempts": ApplicationAttempt,
        "proof_artifacts": ProofArtifact,
        "review_tasks": ReviewTask,
        "candidates": Candidate,
    }
    counts: dict[str, int] = {}
    for name, model in tables.items():
        counts[name] = int((await db.execute(select(func.count(model.id)).where(model.tenant_id.is_(None)))).scalar() or 0)
    return counts
