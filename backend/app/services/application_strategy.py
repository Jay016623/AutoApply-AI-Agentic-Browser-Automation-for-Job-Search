"""Application strategy layer for shortlist/priority selection.

Additive policy layer to avoid "apply everything" behavior.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import ApplicationStatus
from app.core.matching.job_scoring_engine import JobScoringEngine
from app.models.application import Application
from app.models.job import Job
from app.models.resume import Resume


@dataclass(frozen=True)
class StrategyDecision:
    shortlist_application_ids: list[str]
    priority_ranking: list[tuple[str, float]]
    allowed: bool
    reason: str


class ApplicationStrategyLayer:
    """Evaluate application strategy constraints before apply execution."""

    def __init__(
        self,
        *,
        daily_cap_per_candidate: int = 10,
        top_n: int = 5,
        low_quality_sources: set[str] | None = None,
        preferred_companies: set[str] | None = None,
    ) -> None:
        self.daily_cap_per_candidate = daily_cap_per_candidate
        self.top_n = top_n
        self.low_quality_sources = low_quality_sources or {"unknown"}
        self.preferred_companies = preferred_companies or set()

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        application_id: str,
        tenant_id: str | None,
        resume_id: str | None,
    ) -> StrategyDecision:
        app_query = select(Application).where(Application.id == application_id)
        if tenant_id is not None:
            app_query = app_query.where(Application.tenant_id == tenant_id)
        app = (await db.execute(app_query)).scalar_one_or_none()
        if app is None:
            return StrategyDecision([], [], False, "application_not_found")

        candidate_id: str | None = None
        resume = None
        if resume_id:
            resume = (await db.execute(select(Resume).where(Resume.id == resume_id))).scalar_one_or_none()
            candidate_id = resume.candidate_id if resume is not None else None

        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        daily_count_query = select(func.count(Application.id)).where(
            Application.created_at >= day_start,
            Application.status.in_([
                ApplicationStatus.APPLIED,
                ApplicationStatus.APPLYING,
                ApplicationStatus.APPROVED,
            ]),
        )
        if tenant_id is not None:
            daily_count_query = daily_count_query.where(Application.tenant_id == tenant_id)

        if candidate_id is not None:
            daily_count_query = daily_count_query.join(Resume, Resume.id == Application.resume_id).where(
                Resume.candidate_id == candidate_id,
            )

        daily_count = int((await db.execute(daily_count_query)).scalar() or 0)
        if daily_count >= self.daily_cap_per_candidate:
            return StrategyDecision([], [], False, "daily_cap_reached")

        ready_query = (
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(Application.status == ApplicationStatus.APPROVED)
        )
        if tenant_id is not None:
            ready_query = ready_query.where(Application.tenant_id == tenant_id)

        if candidate_id is not None:
            ready_query = ready_query.join(Resume, Resume.id == Application.resume_id, isouter=True).where(
                and_(Resume.candidate_id == candidate_id),
            )

        rows = (await db.execute(ready_query)).all()

        scorer = JobScoringEngine()
        historical_response_companies = await self._response_friendly_companies(db, tenant_id)

        scored: list[tuple[str, str, float]] = []
        for candidate_app, job in rows:
            if job.platform.lower() in self.low_quality_sources:
                continue
            score = float(job.match_score or 0.0)
            if score <= 0:
                score = scorer.score(job=job, resume=resume).score
            if job.company in historical_response_companies or job.company in self.preferred_companies:
                score += 10.0
            scored.append((candidate_app.id, job.company, score))

        if not scored:
            return StrategyDecision([], [], True, "no_competing_ready_items")

        # Avoid duplicate companies by keeping only highest score per company.
        best_by_company: dict[str, tuple[str, float]] = {}
        for app_id, company, score in scored:
            current = best_by_company.get(company)
            if current is None or score > current[1]:
                best_by_company[company] = (app_id, score)

        deduped = sorted(best_by_company.values(), key=lambda x: x[1], reverse=True)
        ranked = deduped[: self.top_n]
        shortlist_ids = [app_id for app_id, _ in ranked]
        priorities = [(app_id, round(score, 2)) for app_id, score in ranked]

        if application_id not in shortlist_ids:
            return StrategyDecision(shortlist_ids, priorities, False, "not_in_top_shortlist")
        return StrategyDecision(shortlist_ids, priorities, True, "selected")

    async def _response_friendly_companies(
        self,
        db: AsyncSession,
        tenant_id: str | None,
    ) -> set[str]:
        query = (
            select(Job.company, func.count(Application.id).label("total"), func.sum(
                case((Application.status.in_([ApplicationStatus.INTERVIEW, ApplicationStatus.OFFER]), 1), else_=0)
            ).label("positive"))
            .join(Application, Application.job_id == Job.id)
            .group_by(Job.company)
        )
        if tenant_id is not None:
            query = query.where(Application.tenant_id == tenant_id)

        companies = set()
        for company, total, positive in (await db.execute(query)).all():
            total = int(total or 0)
            positive = int(positive or 0)
            if total >= 3 and total > 0 and (positive / total) >= 0.2:
                companies.add(company)
        return companies
