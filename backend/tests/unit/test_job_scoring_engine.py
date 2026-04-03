"""Unit tests for additive weighted job scoring engine."""

from datetime import UTC, datetime, timedelta

from app.core.matching.job_scoring_engine import JobScoringEngine
from app.models.job import Job
from app.models.resume import Resume


class TestJobScoringEngine:
    def test_scores_apply_for_strong_alignment(self):
        job = Job(
            platform="linkedin",
            platform_job_id="x1",
            title="Senior Python Engineer",
            company="Google",
            location="Remote",
            remote=True,
            url="https://example.com",
            description="Python FastAPI developer with 5 years experience. No sponsorship.",
            skills_required={"required": ["python", "fastapi"], "preferred": ["aws"]},
            posted_date=datetime.now(UTC) - timedelta(days=2),
            status="new",
        )
        resume = Resume(
            name="R",
            type="base",
            template_id="modern",
            content_text=(
                "Senior Python Engineer with 6 years experience in FastAPI and AWS. "
                "Authorized to work in the US."
            ),
            ats_score=0.85,
        )

        result = JobScoringEngine().score(job=job, resume=resume)

        assert result.score >= 70
        assert result.recommendation == "apply"
        assert 0 <= result.confidence <= 1

    def test_scores_skip_for_poor_alignment(self):
        job = Job(
            platform="indeed",
            platform_job_id="x2",
            title="Senior Java Architect",
            company="Unknown",
            location="Onsite Berlin",
            remote=False,
            url="https://example.com",
            description="Java Spring role requiring 10 years and no sponsorship",
            skills_required={"required": ["java", "spring"]},
            status="new",
        )
        resume = Resume(
            name="R",
            type="base",
            template_id="modern",
            content_text="Junior designer with Figma and Photoshop skills",
            ats_score=0.2,
        )

        result = JobScoringEngine().score(job=job, resume=resume)

        assert result.score < 50
        assert result.recommendation in {"skip", "review"}
        assert result.risk_level in {"medium", "high"}
