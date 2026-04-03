"""Unit tests for execution tenant backfill planning helper."""

from app.models.application import Application
from app.models.audit_log import AuditLog
from app.models.candidate import Candidate
from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.services.tenant_execution_backfill import build_execution_tenant_backfill_plan


class TestExecutionTenantBackfillPlan:
    async def test_counts_missing_tenant_records(self, db_session):
        candidate = Candidate(
            full_name="Jane Doe",
            email="jane@example.com",
            tenant_id="tenant-a",
        )
        db_session.add(candidate)
        await db_session.commit()
        await db_session.refresh(candidate)

        resume = Resume(name="Base", type="base", template_id="modern", candidate_id=candidate.id)
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        job_a = Job(
            tenant_id=None,
            platform="linkedin",
            platform_job_id="ext-a",
            title="Job A",
            company="Co",
            location="Remote",
            url="https://example.com/a",
            description="desc",
            status="new",
        )
        job_b = Job(
            tenant_id="tenant-a",
            platform="linkedin",
            platform_job_id="ext-b",
            title="Job B",
            company="Co",
            location="Remote",
            url="https://example.com/b",
            description="desc",
            status="new",
        )
        db_session.add_all([job_a, job_b])
        await db_session.commit()
        await db_session.refresh(job_a)
        await db_session.refresh(job_b)

        app_missing = Application(job_id=job_a.id, apply_mode="review", status="queued", tenant_id=None)
        app_scoped = Application(job_id=job_b.id, apply_mode="review", status="queued", tenant_id="tenant-a")
        rv_missing = ResumeVersion(
            tenant_id=None,
            candidate_id=candidate.id,
            resume_id=resume.id,
            job_id=None,
            version=1,
            label="v1",
            template_id="modern",
            variant_type="base",
        )
        audit_missing = AuditLog(
            tenant_id=None,
            entity_type="application",
            entity_id="app-1",
            event_type="created",
            message="",
        )

        db_session.add_all([app_missing, app_scoped, rv_missing, audit_missing])
        await db_session.commit()

        plan = await build_execution_tenant_backfill_plan(db_session)

        assert plan.applications_missing_tenant >= 1
        assert plan.resume_versions_missing_tenant >= 1
        assert plan.audit_logs_missing_tenant >= 1
