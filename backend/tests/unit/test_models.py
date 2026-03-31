"""Tests for SQLAlchemy ORM models."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application import Application
from app.models.candidate import Candidate
from app.models.candidate_profile_snapshot import CandidateProfileSnapshot
from app.models.cover_letter_version import CoverLetterVersion
from app.models.job import Job
from app.models.llm_usage import LLMUsage
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion
from app.models.user_settings import UserSettings


class TestJobModel:
    """Test Job model CRUD operations."""

    async def test_create_job_with_required_fields(
        self,
        db_session: AsyncSession,
        sample_job_data: dict,
    ) -> None:
        """Job should be created with all required fields."""
        job = Job(**sample_job_data)
        db_session.add(job)
        await db_session.commit()

        result = await db_session.execute(select(Job).where(Job.id == job.id))
        fetched = result.scalar_one()

        assert fetched.title == "Senior Python Developer"
        assert fetched.company == "TechCorp Inc."
        assert fetched.platform == "linkedin"
        assert fetched.remote is True
        assert fetched.match_score == 0.85
        assert fetched.status == "new"

    async def test_job_has_auto_generated_uuid(
        self,
        db_session: AsyncSession,
        sample_job_data: dict,
    ) -> None:
        """Job should have an auto-generated UUID primary key."""
        job = Job(**sample_job_data)
        db_session.add(job)
        await db_session.commit()

        assert job.id is not None
        assert len(job.id) == 32  # UUID hex without dashes

    async def test_job_has_timestamps(
        self,
        db_session: AsyncSession,
        sample_job_data: dict,
    ) -> None:
        """Job should have created_at and updated_at timestamps."""
        job = Job(**sample_job_data)
        db_session.add(job)
        await db_session.commit()

        assert job.created_at is not None
        assert job.updated_at is not None

    async def test_job_repr(self, sample_job_data: dict) -> None:
        """Job repr should include id, title, and company."""
        job = Job(**sample_job_data)
        repr_str = repr(job)
        assert "Senior Python Developer" in repr_str
        assert "TechCorp Inc." in repr_str


class TestResumeModel:
    """Test Resume model operations."""

    async def test_create_base_resume(self, db_session: AsyncSession) -> None:
        """Base resume should be created without job or parent reference."""
        resume = Resume(
            name="My Resume",
            type="base",
            template_id="modern",
            file_path_pdf="data/generated/resumes/my_resume.pdf",
            file_path_docx="data/generated/resumes/my_resume.docx",
            content_text="Experienced developer...",
        )
        db_session.add(resume)
        await db_session.commit()

        assert resume.id is not None
        assert resume.type == "base"
        assert resume.base_resume_id is None
        assert resume.job_id is None


class TestApplicationModel:
    """Test Application model operations."""

    async def test_create_application_linked_to_job(
        self,
        db_session: AsyncSession,
        sample_job_data: dict,
    ) -> None:
        """Application should link to a job via foreign key."""
        job = Job(**sample_job_data)
        db_session.add(job)
        await db_session.flush()

        application = Application(
            job_id=job.id,
            status="queued",
            apply_mode="review",
        )
        db_session.add(application)
        await db_session.commit()

        assert application.id is not None
        assert application.job_id == job.id
        assert application.status == "queued"


class TestLLMUsageModel:
    """Test LLMUsage model operations."""

    async def test_create_llm_usage_record(self, db_session: AsyncSession) -> None:
        """LLM usage record should store provider, tokens, and cost."""
        usage = LLMUsage(
            provider="openai",
            model="gpt-4o",
            prompt_tokens=150,
            completion_tokens=80,
            total_tokens=230,
            cost_usd=0.00345,
            latency_ms=1200,
            purpose="resume_tailor",
            trace_id="autoapply-abc123",
        )
        db_session.add(usage)
        await db_session.commit()

        result = await db_session.execute(
            select(LLMUsage).where(LLMUsage.id == usage.id)
        )
        fetched = result.scalar_one()

        assert fetched.provider == "openai"
        assert fetched.total_tokens == 230
        assert fetched.cost_usd == pytest.approx(0.00345)
        assert fetched.purpose == "resume_tailor"


class TestUserSettingsModel:
    """Test UserSettings singleton model."""

    async def test_create_default_settings(self, db_session: AsyncSession) -> None:
        """Default user settings should be created with singleton id."""
        settings = UserSettings()
        db_session.add(settings)
        await db_session.commit()

        assert settings.id == "singleton"
        assert settings.apply_mode == "review"
        assert settings.max_parallel == 3
        assert settings.min_ats_score == 0.75


class TestCandidateDomainModels:
    """Test candidate-centric models and basic constraints."""

    async def test_create_candidate_and_versions(self, db_session: AsyncSession) -> None:
        candidate = Candidate(
            tenant_id="tenant-1",
            full_name="John Smith",
            email="john@example.com",
        )
        db_session.add(candidate)
        await db_session.flush()

        snapshot = CandidateProfileSnapshot(
            tenant_id="tenant-1",
            candidate_id=candidate.id,
            version=1,
            summary="Profile v1",
            skills=["python"],
            experience=[],
            education=[],
            certifications=[],
        )
        resume_version = ResumeVersion(
            tenant_id="tenant-1",
            candidate_id=candidate.id,
            version=1,
            label="Resume v1",
            template_id="modern",
            variant_type="base",
        )
        cover_version = CoverLetterVersion(
            tenant_id="tenant-1",
            candidate_id=candidate.id,
            version=1,
            label="Cover v1",
            template_id="standard",
        )
        db_session.add_all([snapshot, resume_version, cover_version])
        await db_session.commit()

        result = await db_session.execute(
            select(Candidate).where(Candidate.id == candidate.id),
        )
        fetched = result.scalar_one()
        assert fetched.email == "john@example.com"
        assert fetched.profile_snapshots[0].version == 1
        assert fetched.resume_versions[0].variant_type == "base"
        assert fetched.cover_letter_versions[0].template_id == "standard"
