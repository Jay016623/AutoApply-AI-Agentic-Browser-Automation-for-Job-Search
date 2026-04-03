"""Unit tests for application shortlist strategy layer."""

from app.config.constants import ApplicationStatus
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume
from app.services.application_strategy import ApplicationStrategyLayer


async def _create_job(db_session, sample_job_data, suffix: str, company: str, platform: str = "linkedin"):
    data = {**sample_job_data, "platform_job_id": f"st-{suffix}", "company": company, "platform": platform}
    job = Job(**data)
    db_session.add(job)
    await db_session.commit()
    await db_session.refresh(job)
    return job


class TestApplicationStrategyLayer:
    async def test_selects_top_n_and_avoids_duplicate_company(self, db_session, sample_job_data):
        resume = Resume(name="R", type="base", template_id="modern", content_text="python fastapi")
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        j1 = await _create_job(db_session, sample_job_data, "1", company="Alpha", platform="linkedin")
        j1.match_score = 92
        j2 = await _create_job(db_session, sample_job_data, "2", company="Alpha", platform="linkedin")
        j2.match_score = 75
        j3 = await _create_job(db_session, sample_job_data, "3", company="Beta", platform="indeed")
        j3.match_score = 88
        await db_session.commit()

        a1 = Application(job_id=j1.id, resume_id=resume.id, status=ApplicationStatus.APPROVED, apply_mode="review")
        a2 = Application(job_id=j2.id, resume_id=resume.id, status=ApplicationStatus.APPROVED, apply_mode="review")
        a3 = Application(job_id=j3.id, resume_id=resume.id, status=ApplicationStatus.APPROVED, apply_mode="review")
        db_session.add_all([a1, a2, a3])
        await db_session.commit()
        await db_session.refresh(a1)

        decision = await ApplicationStrategyLayer(top_n=2).evaluate(
            db_session,
            application_id=a1.id,
            tenant_id=None,
            resume_id=resume.id,
        )

        assert decision.allowed is True
        assert len(decision.shortlist_application_ids) == 2
        assert a2.id not in decision.shortlist_application_ids

    async def test_blocks_when_daily_cap_reached(self, db_session, sample_job_data):
        resume = Resume(name="R", type="base", template_id="modern", content_text="python")
        db_session.add(resume)
        await db_session.commit()
        await db_session.refresh(resume)

        job = await _create_job(db_session, sample_job_data, "cap", company="CapCo")
        app = Application(job_id=job.id, resume_id=resume.id, status=ApplicationStatus.APPROVED, apply_mode="review")
        db_session.add(app)
        await db_session.commit()
        await db_session.refresh(app)

        decision = await ApplicationStrategyLayer(daily_cap_per_candidate=0).evaluate(
            db_session,
            application_id=app.id,
            tenant_id=None,
            resume_id=resume.id,
        )

        assert decision.allowed is False
        assert decision.reason == "daily_cap_reached"
