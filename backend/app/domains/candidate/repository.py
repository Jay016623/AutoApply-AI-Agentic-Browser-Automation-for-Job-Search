"""Repository layer for candidate domain persistence."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.models.candidate import Candidate
from app.models.candidate_profile_snapshot import CandidateProfileSnapshot
from app.models.cover_letter_version import CoverLetterVersion
from app.models.resume_version import ResumeVersion


class CandidateRepository:
    """Persistence abstraction for candidate domain entities."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_candidates(self, tenant_id: str | None = None) -> tuple[list[Candidate], int]:
        query = select(Candidate).order_by(Candidate.created_at.desc())
        count_q = select(func.count(Candidate.id))

        if tenant_id:
            query = query.where(Candidate.tenant_id == tenant_id)
            count_q = count_q.where(Candidate.tenant_id == tenant_id)

        result = await self._db.execute(query)
        count_result = await self._db.execute(count_q)
        return list(result.scalars().all()), int(count_result.scalar() or 0)

    async def create_candidate(self, candidate: Candidate) -> Candidate:
        self._db.add(candidate)
        await self._db.commit()
        await self._db.refresh(candidate)
        return candidate

    async def get_candidate(self, candidate_id: str) -> Candidate:
        result = await self._db.execute(
            select(Candidate).where(Candidate.id == candidate_id),
        )
        candidate = result.scalar_one_or_none()
        if candidate is None:
            raise RecordNotFoundError("Candidate", candidate_id)
        return candidate

    async def save(self, candidate: Candidate) -> Candidate:
        await self._db.commit()
        await self._db.refresh(candidate)
        return candidate

    async def create_profile_snapshot(
        self,
        snapshot: CandidateProfileSnapshot,
    ) -> CandidateProfileSnapshot:
        self._db.add(snapshot)
        await self._db.commit()
        await self._db.refresh(snapshot)
        return snapshot

    async def get_next_profile_version(self, candidate_id: str) -> int:
        result = await self._db.execute(
            select(func.max(CandidateProfileSnapshot.version)).where(
                CandidateProfileSnapshot.candidate_id == candidate_id,
            ),
        )
        max_version = result.scalar()
        return (int(max_version) + 1) if max_version is not None else 1

    async def list_profile_snapshots(self, candidate_id: str) -> list[CandidateProfileSnapshot]:
        result = await self._db.execute(
            select(CandidateProfileSnapshot)
            .where(CandidateProfileSnapshot.candidate_id == candidate_id)
            .order_by(CandidateProfileSnapshot.version.desc()),
        )
        return list(result.scalars().all())

    async def list_resume_versions(self, candidate_id: str) -> list[ResumeVersion]:
        result = await self._db.execute(
            select(ResumeVersion)
            .where(ResumeVersion.candidate_id == candidate_id)
            .order_by(ResumeVersion.version.desc()),
        )
        return list(result.scalars().all())

    async def list_cover_letter_versions(self, candidate_id: str) -> list[CoverLetterVersion]:
        result = await self._db.execute(
            select(CoverLetterVersion)
            .where(CoverLetterVersion.candidate_id == candidate_id)
            .order_by(CoverLetterVersion.version.desc()),
        )
        return list(result.scalars().all())
