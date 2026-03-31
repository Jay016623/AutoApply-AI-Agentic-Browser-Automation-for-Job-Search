"""Candidate domain service layer."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.candidate.repository import CandidateRepository
from app.models.candidate import Candidate
from app.models.candidate_profile_snapshot import CandidateProfileSnapshot
from app.schemas.candidate import (
    CandidateCreate,
    CandidateListResponse,
    CandidateProfileSnapshotCreate,
    CandidateProfileSnapshotResponse,
    CandidateResponse,
    CandidateSettingsSchema,
    CandidateUpdate,
    CoverLetterVersionResponse,
    ResumeVersionResponse,
)


class CandidateService:
    """Application service for candidate CRUD and version metadata."""

    def __init__(self, db: AsyncSession) -> None:
        self._repo = CandidateRepository(db)

    async def list_candidates(self, tenant_id: str | None = None) -> CandidateListResponse:
        items, total = await self._repo.list_candidates(tenant_id=tenant_id)
        return CandidateListResponse(
            items=[CandidateResponse.model_validate(i) for i in items],
            total=total,
        )

    async def create_candidate(self, data: CandidateCreate) -> CandidateResponse:
        candidate = Candidate(
            tenant_id=data.tenant_id,
            full_name=data.full_name,
            email=str(data.email),
            phone=data.phone,
            location=data.location,
            headline=data.headline,
            is_default=data.is_default,
            settings=data.settings.model_dump(),
        )
        created = await self._repo.create_candidate(candidate)
        return CandidateResponse.model_validate(created)

    async def get_candidate(self, candidate_id: str) -> CandidateResponse:
        candidate = await self._repo.get_candidate(candidate_id)
        return CandidateResponse.model_validate(candidate)

    async def update_candidate(self, candidate_id: str, update: CandidateUpdate) -> CandidateResponse:
        candidate = await self._repo.get_candidate(candidate_id)
        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(candidate, key, value)
        updated = await self._repo.save(candidate)
        return CandidateResponse.model_validate(updated)

    async def get_candidate_settings(self, candidate_id: str) -> CandidateSettingsSchema:
        candidate = await self._repo.get_candidate(candidate_id)
        return CandidateSettingsSchema(**(candidate.settings or {}))

    async def update_candidate_settings(
        self,
        candidate_id: str,
        settings: CandidateSettingsSchema,
    ) -> CandidateSettingsSchema:
        candidate = await self._repo.get_candidate(candidate_id)
        candidate.settings = settings.model_dump()
        await self._repo.save(candidate)
        return CandidateSettingsSchema(**(candidate.settings or {}))

    async def create_profile_snapshot(
        self,
        candidate_id: str,
        payload: CandidateProfileSnapshotCreate,
    ) -> CandidateProfileSnapshotResponse:
        candidate = await self._repo.get_candidate(candidate_id)
        next_version = await self._repo.get_next_profile_version(candidate_id)
        snapshot = CandidateProfileSnapshot(
            tenant_id=candidate.tenant_id,
            candidate_id=candidate.id,
            version=next_version,
            source=payload.source,
            summary=payload.summary,
            skills=payload.skills,
            experience=payload.experience,
            education=payload.education,
            certifications=payload.certifications,
            snapshot_metadata=payload.snapshot_metadata,
        )
        created = await self._repo.create_profile_snapshot(snapshot)
        return CandidateProfileSnapshotResponse.model_validate(created)

    async def list_profile_snapshots(self, candidate_id: str) -> list[CandidateProfileSnapshotResponse]:
        _ = await self._repo.get_candidate(candidate_id)
        rows = await self._repo.list_profile_snapshots(candidate_id)
        return [CandidateProfileSnapshotResponse.model_validate(r) for r in rows]

    async def list_resume_versions(self, candidate_id: str) -> list[ResumeVersionResponse]:
        _ = await self._repo.get_candidate(candidate_id)
        rows = await self._repo.list_resume_versions(candidate_id)
        responses: list[ResumeVersionResponse] = []
        for r in rows:
            responses.append(
                ResumeVersionResponse(
                    id=r.id,
                    candidate_id=r.candidate_id,
                    version=r.version,
                    label=r.label,
                    template_id=r.template_id,
                    variant_type=r.variant_type,
                    job_id=r.job_id,
                    ats_score=r.ats_score,
                    has_pdf=bool(r.file_path_pdf),
                    has_docx=bool(r.file_path_docx),
                    created_at=r.created_at,
                )
            )
        return responses

    async def list_cover_letter_versions(self, candidate_id: str) -> list[CoverLetterVersionResponse]:
        _ = await self._repo.get_candidate(candidate_id)
        rows = await self._repo.list_cover_letter_versions(candidate_id)
        responses: list[CoverLetterVersionResponse] = []
        for r in rows:
            responses.append(
                CoverLetterVersionResponse(
                    id=r.id,
                    candidate_id=r.candidate_id,
                    version=r.version,
                    label=r.label,
                    template_id=r.template_id,
                    job_id=r.job_id,
                    has_pdf=bool(r.file_path_pdf),
                    has_docx=bool(r.file_path_docx),
                    created_at=r.created_at,
                )
            )
        return responses
