"""Tests for feedback loop adjustment outputs."""

from app.config.constants import ApplicationStatus
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.services.feedback_loop import get_feedback_loop_adjustments


class TestFeedbackLoop:
    async def test_returns_defaults_when_no_history(self, db_session):
        feedback = await get_feedback_loop_adjustments(db_session, tenant_id=None)
        assert feedback.strategy_top_n == 5
        assert feedback.strategy_daily_cap == 10
        assert abs(sum(feedback.scoring_weights.values()) - 1.0) < 1e-6

    async def test_blocks_low_converting_source_and_prefers_company(self, db_session, sample_job_data):
        resume = Resume(name="R", type="base", template_id="modern", content_text="python")
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        for i in range(6):
            job = Job(**{**sample_job_data, "platform_job_id": f"fb-gd-{i}", "platform": "glassdoor", "company": "SlowCo"})
            db_session.add(job)
            await db_session.commit()
            await db_session.refresh(job)
            app = Application(job_id=job.id, resume_id=resume.id, status=ApplicationStatus.APPLIED, apply_mode="review")
            db_session.add(app)
            await db_session.commit()

        for i in range(3):
            job = Job(**{**sample_job_data, "platform_job_id": f"fb-li-{i}", "platform": "linkedin", "company": "FastCo"})
            db_session.add(job)
            await db_session.commit()
            await db_session.refresh(job)
            status = ApplicationStatus.INTERVIEW if i < 2 else ApplicationStatus.APPLIED
            app = Application(job_id=job.id, resume_id=resume.id, status=status, apply_mode="review")
            db_session.add(app)
            await db_session.commit()

        feedback = await get_feedback_loop_adjustments(db_session, tenant_id=None)
        assert "glassdoor" in feedback.blocked_sources
        assert "FastCo" in feedback.preferred_companies
