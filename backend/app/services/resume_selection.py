"""Decision layer for selecting the best resume version per job.

This layer is additive and does not replace resume generation itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.job import Job
from app.models.resume import Resume
from app.models.resume_version import ResumeVersion


@dataclass(frozen=True)
class ResumeSelectionDecision:
    selected_resume: Resume | None
    should_tailor: bool
    reason: str
    fit_score: float


def _fit_score(job: Job, resume_text: str | None, ats_score: float | None) -> float:
    text = (resume_text or "").lower()
    if not text:
        return 0.0
    job_tokens = set((job.description or job.title or "").lower().split())
    resume_tokens = set(text.split())
    if not job_tokens:
        overlap = 0.5
    else:
        overlap = len(job_tokens & resume_tokens) / len(job_tokens)
    ats_component = float(ats_score) if ats_score is not None else 0.5
    return max(0.0, min(1.0, overlap * 0.65 + ats_component * 0.35))


async def select_best_resume_for_job(
    db: AsyncSession,
    *,
    base_resume_id: str,
    job_id: str,
    max_tailored_versions_per_job: int = 3,
    base_fit_keep_threshold: float = 0.72,
) -> ResumeSelectionDecision:
    base_resume = (await db.execute(select(Resume).where(Resume.id == base_resume_id))).scalar_one_or_none()
    if base_resume is None:
        return ResumeSelectionDecision(None, False, "base_resume_not_found", 0.0)

    job = (await db.execute(select(Job).where(Job.id == job_id))).scalar_one_or_none()
    if job is None:
        return ResumeSelectionDecision(base_resume, False, "job_not_found_fallback_base", 0.0)

    base_fit = _fit_score(job, base_resume.content_text, base_resume.ats_score)

    candidate_id = base_resume.candidate_id
    if not candidate_id:
        if base_fit >= base_fit_keep_threshold:
            return ResumeSelectionDecision(base_resume, False, "base_fit_sufficient", base_fit)
        return ResumeSelectionDecision(base_resume, True, "no_candidate_history_tailor", base_fit)

    tailored_versions = (
        await db.execute(
            select(ResumeVersion)
            .where(
                ResumeVersion.candidate_id == candidate_id,
                ResumeVersion.job_id == job_id,
                ResumeVersion.variant_type == "tailored",
            )
            .order_by(ResumeVersion.created_at.desc()),
        )
    ).scalars().all()

    best_existing_resume: Resume | None = None
    best_existing_fit = 0.0
    for version in tailored_versions:
        if not version.resume_id:
            continue
        resume = (await db.execute(select(Resume).where(Resume.id == version.resume_id))).scalar_one_or_none()
        if resume is None:
            continue
        fit = _fit_score(job, resume.content_text, resume.ats_score)
        if fit > best_existing_fit:
            best_existing_fit = fit
            best_existing_resume = resume

    if len(tailored_versions) >= max_tailored_versions_per_job and best_existing_resume is not None:
        return ResumeSelectionDecision(
            best_existing_resume,
            False,
            "tailoring_cap_reached_use_best_existing",
            best_existing_fit,
        )

    if best_existing_resume is not None and best_existing_fit >= (base_fit + 0.05):
        return ResumeSelectionDecision(
            best_existing_resume,
            False,
            "best_existing_tailored_selected",
            best_existing_fit,
        )

    if base_fit >= base_fit_keep_threshold:
        return ResumeSelectionDecision(base_resume, False, "base_fit_sufficient", base_fit)

    return ResumeSelectionDecision(base_resume, True, "tailor_new_version", base_fit)
