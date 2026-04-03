"""Feedback loop for adapting scoring, selection, and resume strategy."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import ApplicationStatus
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume

RESPONDED_STATUSES = {ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER}


@dataclass(frozen=True)
class FeedbackAdjustments:
    scoring_weights: dict[str, float]
    preferred_companies: set[str]
    blocked_sources: set[str]
    strategy_top_n: int
    strategy_daily_cap: int
    max_tailored_versions_per_job: int
    base_fit_keep_threshold: float


async def get_feedback_loop_adjustments(
    db: AsyncSession,
    *,
    tenant_id: str | None,
) -> FeedbackAdjustments:
    base_weights = {
        "role_fit": 0.2,
        "skills_match": 0.2,
        "experience_gap": 0.12,
        "location_fit": 0.08,
        "visa_compatibility": 0.08,
        "company_quality": 0.07,
        "recency_of_job": 0.1,
        "resume_strength_for_job": 0.15,
    }

    app_job_query = select(Application.status, Application.resume_id, Job.company, Job.platform).join(
        Job,
        Job.id == Application.job_id,
    )
    if tenant_id is not None:
        app_job_query = app_job_query.where(Application.tenant_id == tenant_id)
    rows = (await db.execute(app_job_query)).all()

    if not rows:
        return FeedbackAdjustments(base_weights, set(), set(), 5, 10, 3, 0.72)

    total = len(rows)
    responded = sum(1 for status, *_ in rows if status in RESPONDED_STATUSES)
    response_rate = responded / max(1, total)

    company_totals: dict[str, tuple[int, int]] = {}
    source_totals: dict[str, tuple[int, int]] = {}
    resume_totals: dict[str, tuple[int, int]] = {}

    for status, resume_id, company, platform in rows:
        is_resp = 1 if status in RESPONDED_STATUSES else 0

        c_total, c_resp = company_totals.get(company, (0, 0))
        company_totals[company] = (c_total + 1, c_resp + is_resp)

        s_total, s_resp = source_totals.get(platform, (0, 0))
        source_totals[platform] = (s_total + 1, s_resp + is_resp)

        if resume_id:
            r_total, r_resp = resume_totals.get(resume_id, (0, 0))
            resume_totals[resume_id] = (r_total + 1, r_resp + is_resp)

    preferred_companies = {
        company
        for company, (t, r) in company_totals.items()
        if t >= 3 and (r / max(1, t)) >= 0.2
    }
    blocked_sources = {
        source
        for source, (t, r) in source_totals.items()
        if t >= 5 and (r / max(1, t)) < 0.05
    }

    # Resume effectiveness: if historically strong resumes correlate with responses,
    # boost resume_strength dimension slightly.
    if resume_totals:
        avg_resume_conversion = sum(r / max(1, t) for t, r in resume_totals.values()) / len(resume_totals)
    else:
        avg_resume_conversion = 0.0

    scoring_weights = dict(base_weights)
    if avg_resume_conversion > 0.2:
        scoring_weights["resume_strength_for_job"] = 0.2
        scoring_weights["company_quality"] = 0.08
        scoring_weights["recency_of_job"] = 0.08

    if response_rate < 0.08:
        strategy_top_n = 4
        strategy_daily_cap = 8
        max_tailored_versions_per_job = 2
        base_fit_threshold = 0.78
    elif response_rate > 0.2:
        strategy_top_n = 7
        strategy_daily_cap = 12
        max_tailored_versions_per_job = 4
        base_fit_threshold = 0.68
    else:
        strategy_top_n = 5
        strategy_daily_cap = 10
        max_tailored_versions_per_job = 3
        base_fit_threshold = 0.72

    # Normalize scoring weights to sum to 1.
    total_w = sum(scoring_weights.values())
    if total_w > 0:
        scoring_weights = {k: v / total_w for k, v in scoring_weights.items()}

    return FeedbackAdjustments(
        scoring_weights=scoring_weights,
        preferred_companies=preferred_companies,
        blocked_sources=blocked_sources,
        strategy_top_n=strategy_top_n,
        strategy_daily_cap=strategy_daily_cap,
        max_tailored_versions_per_job=max_tailored_versions_per_job,
        base_fit_keep_threshold=base_fit_threshold,
    )
