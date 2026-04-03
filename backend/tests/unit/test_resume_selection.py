"""Tests for resume decision layer before tailoring."""

from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.services.resume_selection import select_best_resume_for_job


class TestResumeSelection:
    async def test_uses_existing_tailored_when_better(self, db_session, sample_job_data):
        job = Job(**{**sample_job_data, "platform_job_id": "sel-1"})
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        base = Resume(
            name="Base",
            type="base",
            template_id="modern",
            candidate_id="cand-1",
            content_text="generic resume text",
            ats_score=0.4,
        )
        better = Resume(
            name="Tailored",
            type="tailored",
            template_id="modern",
            candidate_id="cand-1",
            job_id=job.id,
            content_text=(job.description or "") + " python fastapi",
            ats_score=0.9,
        )
        db_session.add_all([base, better])
        await db_session.commit()
        await db_session.refresh(base)
        await db_session.refresh(better)

        version = ResumeVersion(
            tenant_id=None,
            candidate_id="cand-1",
            resume_id=better.id,
            job_id=job.id,
            version=1,
            label="v1",
            template_id="modern",
            variant_type="tailored",
        )
        db_session.add(version)
        await db_session.commit()

        decision = await select_best_resume_for_job(
            db_session,
            base_resume_id=base.id,
            job_id=job.id,
        )

        assert decision.selected_resume is not None
        assert decision.selected_resume.id == better.id
        assert decision.should_tailor is False

    async def test_tailors_when_base_fit_low_and_no_good_existing(self, db_session, sample_job_data):
        job = Job(**{**sample_job_data, "platform_job_id": "sel-2"})
        db_session.add(job)
        await db_session.commit()
        await db_session.refresh(job)

        base = Resume(
            name="Base",
            type="base",
            template_id="modern",
            candidate_id="cand-2",
            content_text="totally unrelated profile",
            ats_score=0.1,
        )
        db_session.add(base)
        await db_session.commit()
        await db_session.refresh(base)

        decision = await select_best_resume_for_job(
            db_session,
            base_resume_id=base.id,
            job_id=job.id,
        )

        assert decision.selected_resume is not None
        assert decision.selected_resume.id == base.id
        assert decision.should_tailor is True
