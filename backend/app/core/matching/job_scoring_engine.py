"""Additive weighted job scoring engine.

This module is intentionally separate from the existing matching pipeline.
It provides operational scoring signals without replacing current flows.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.models.job import Job
from app.models.resume import Resume

_WORD_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9+#.]{1,}")
_YEAR_REQ_RE = re.compile(r"(\d{1,2})\+?\s+years", re.IGNORECASE)


@dataclass(frozen=True)
class JobScoreResult:
    score: float
    confidence: float
    risk_level: str
    recommendation: str
    dimensions: dict[str, float]


class JobScoringEngine:
    """Heuristic weighted scorer for apply decision support."""

    def __init__(self, weights_override: dict[str, float] | None = None) -> None:
        self._weights_override = weights_override or {}

    def score(
        self,
        *,
        job: Job,
        resume: Resume | None,
    ) -> JobScoreResult:
        dimensions = {
            "role_fit": self._role_fit(job, resume),
            "skills_match": self._skills_match(job, resume),
            "experience_gap": self._experience_gap(job, resume),
            "location_fit": self._location_fit(job, resume),
            "visa_compatibility": self._visa_compatibility(job, resume),
            "company_quality": self._company_quality(job),
            "recency_of_job": self._recency(job),
            "resume_strength_for_job": self._resume_strength(job, resume),
        }
        weights = {
            "role_fit": 0.2,
            "skills_match": 0.2,
            "experience_gap": 0.12,
            "location_fit": 0.08,
            "visa_compatibility": 0.08,
            "company_quality": 0.07,
            "recency_of_job": 0.1,
            "resume_strength_for_job": 0.15,
        }
        weights.update({k: v for k, v in self._weights_override.items() if k in weights and v >= 0})
        weight_sum = sum(weights.values())
        if weight_sum > 0:
            weights = {k: v / weight_sum for k, v in weights.items()}

        raw_score = sum(dimensions[key] * weights[key] for key in dimensions)
        score = round(max(0.0, min(100.0, raw_score * 100.0)), 2)

        populated_dims = sum(1 for v in dimensions.values() if v > 0)
        confidence = round(min(1.0, 0.35 + (populated_dims / len(dimensions)) * 0.65), 2)

        if score >= 75 and confidence >= 0.65:
            recommendation = "apply"
            risk_level = "low"
        elif score < 45:
            recommendation = "skip"
            risk_level = "high"
        else:
            recommendation = "review"
            risk_level = "medium"

        return JobScoreResult(
            score=score,
            confidence=confidence,
            risk_level=risk_level,
            recommendation=recommendation,
            dimensions={k: round(v, 3) for k, v in dimensions.items()},
        )

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {m.group(0).lower() for m in _WORD_RE.finditer(text or "")}

    def _role_fit(self, job: Job, resume: Resume | None) -> float:
        if resume is None:
            return 0.45
        title_t = self._tokens(job.title)
        resume_t = self._tokens((resume.content_text or "")[:500])
        if not title_t or not resume_t:
            return 0.4
        overlap = len(title_t & resume_t) / len(title_t)
        return min(1.0, 0.35 + overlap * 0.65)

    def _skills_match(self, job: Job, resume: Resume | None) -> float:
        skills = job.skills_required if isinstance(job.skills_required, dict) else {}
        required = [str(s).lower() for s in skills.get("required", skills.get("skills", []))]
        preferred = [str(s).lower() for s in skills.get("preferred", [])]
        if not required and not preferred:
            return 0.6
        resume_text = (resume.content_text or "").lower() if resume is not None else ""
        req_hit = sum(1 for s in required if s and s in resume_text)
        pref_hit = sum(1 for s in preferred if s and s in resume_text)
        req_ratio = req_hit / max(1, len(required))
        pref_ratio = pref_hit / max(1, len(preferred)) if preferred else 0.5
        return min(1.0, req_ratio * 0.75 + pref_ratio * 0.25)

    def _experience_gap(self, job: Job, resume: Resume | None) -> float:
        desc = job.description or ""
        req_years = max((int(m.group(1)) for m in _YEAR_REQ_RE.finditer(desc)), default=0)
        if req_years <= 0:
            return 0.65
        resume_years = max((int(m.group(1)) for m in _YEAR_REQ_RE.finditer((resume.content_text if resume else ""))), default=0)
        if resume_years <= 0:
            return 0.35
        ratio = resume_years / req_years
        return max(0.0, min(1.0, ratio))

    def _location_fit(self, job: Job, resume: Resume | None) -> float:
        if job.remote:
            return 1.0
        location = (job.location or "").lower()
        if not location:
            return 0.55
        resume_text = (resume.content_text or "").lower() if resume else ""
        if location and location in resume_text:
            return 0.9
        return 0.5

    def _visa_compatibility(self, job: Job, resume: Resume | None) -> float:
        desc = (job.description or "").lower()
        resume_text = (resume.content_text or "").lower() if resume else ""
        needs_auth = "no sponsorship" in desc or "authorized to work" in desc
        if not needs_auth:
            return 0.7
        if "authorized" in resume_text or "work authorization" in resume_text:
            return 1.0
        return 0.3

    def _company_quality(self, job: Job) -> float:
        company = (job.company or "").lower()
        trusted = {"google", "microsoft", "amazon", "meta", "apple", "netflix"}
        if any(x in company for x in trusted):
            return 0.9
        if len(company) >= 3:
            return 0.6
        return 0.5

    def _recency(self, job: Job) -> float:
        if job.posted_date is None:
            return 0.55
        now = datetime.now(UTC)
        posted = job.posted_date if job.posted_date.tzinfo else job.posted_date.replace(tzinfo=UTC)
        age_days = max(0.0, (now - posted).total_seconds() / 86400)
        return max(0.0, min(1.0, math.exp(-age_days / 30.0)))

    def _resume_strength(self, job: Job, resume: Resume | None) -> float:
        if resume is None:
            return 0.4
        if resume.ats_score is not None:
            return max(0.0, min(1.0, float(resume.ats_score)))
        text = (resume.content_text or "")
        if not text:
            return 0.3
        job_tokens = self._tokens(job.description or job.title)
        resume_tokens = self._tokens(text)
        if not job_tokens:
            return 0.55
        return len(job_tokens & resume_tokens) / len(job_tokens)
