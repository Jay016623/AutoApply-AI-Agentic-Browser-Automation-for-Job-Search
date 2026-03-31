"""Candidate domain boundary package."""

from app.domains.candidate.repository import CandidateRepository
from app.domains.candidate.service import CandidateService

__all__ = ["CandidateRepository", "CandidateService"]
