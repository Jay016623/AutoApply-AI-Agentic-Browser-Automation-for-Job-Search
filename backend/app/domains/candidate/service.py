"""Candidate domain service layer."""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role, ensure_role, ensure_tenant_access, require_tenant
from app.config.settings import get_settings
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
from app.services import control_plane


class CandidateService:
    """Application service for candidate CRUD and version metadata."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = CandidateRepository(db)

    async def list_candidates(self, auth: AuthContext, tenant_id: str | None = None) -> CandidateListResponse:
        scoped_tenant = tenant_id or auth.tenant_id
        if auth.enforced:
            scoped_tenant = require_tenant(auth)
        items, total = await self._repo.list_candidates(tenant_id=scoped_tenant)
        return CandidateListResponse(
            items=[CandidateResponse.model_validate(i) for i in items],
            total=total,
        )

    async def create_candidate(self, data: CandidateCreate, auth: AuthContext) -> CandidateResponse:
        ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.RECRUITER, Role.OPERATOR})
        if auth.enforced:
            tenant_id = require_tenant(auth)
            if data.tenant_id and data.tenant_id != tenant_id:
                raise HTTPException(status_code=403, detail="cross_tenant_candidate_create_denied")
            data = data.model_copy(update={"tenant_id": tenant_id})
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
        if candidate.tenant_id is None and not get_settings().feature_flags.allow_legacy_unscoped_writes:
            raise HTTPException(status_code=400, detail="tenant_id_required_for_candidate_create")
        if candidate.tenant_id:
            try:
                await control_plane.enforce_quota(
                    self._db,
                    tenant_id=candidate.tenant_id,
                    quota_key="candidate_count",
                    increment=1,
                    actor_id=auth.user_id,
                    actor_type="user",
                    context={"operation": "create_candidate"},
                )
            except control_plane.QuotaExceededError as exc:
                raise HTTPException(status_code=402, detail=str(exc)) from exc
        created = await self._repo.create_candidate(candidate)
        return CandidateResponse.model_validate(created)

    async def get_candidate(self, candidate_id: str, auth: AuthContext) -> CandidateResponse:
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        return CandidateResponse.model_validate(candidate)

    async def update_candidate(self, candidate_id: str, update: CandidateUpdate, auth: AuthContext) -> CandidateResponse:
        ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.RECRUITER, Role.OPERATOR})
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        for key, value in update.model_dump(exclude_unset=True).items():
            setattr(candidate, key, value)
        updated = await self._repo.save(candidate)
        return CandidateResponse.model_validate(updated)

    async def get_candidate_settings(self, candidate_id: str, auth: AuthContext) -> CandidateSettingsSchema:
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        return CandidateSettingsSchema(**(candidate.settings or {}))

    async def update_candidate_settings(
        self,
        candidate_id: str,
        settings: CandidateSettingsSchema,
        auth: AuthContext,
    ) -> CandidateSettingsSchema:
        ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.RECRUITER, Role.OPERATOR})
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        candidate.settings = settings.model_dump()
        await self._repo.save(candidate)
        return CandidateSettingsSchema(**(candidate.settings or {}))

    async def create_profile_snapshot(
        self,
        candidate_id: str,
        payload: CandidateProfileSnapshotCreate,
        auth: AuthContext,
    ) -> CandidateProfileSnapshotResponse:
        ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.RECRUITER, Role.OPERATOR})
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        next_version = await self._repo.get_next_profile_version(candidate_id, tenant_id=candidate.tenant_id)
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

    async def list_profile_snapshots(self, candidate_id: str, auth: AuthContext) -> list[CandidateProfileSnapshotResponse]:
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        rows = await self._repo.list_profile_snapshots(candidate_id, tenant_id=candidate.tenant_id)
        return [CandidateProfileSnapshotResponse.model_validate(r) for r in rows]

    async def list_resume_versions(self, candidate_id: str, auth: AuthContext) -> list[ResumeVersionResponse]:
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        rows = await self._repo.list_resume_versions(candidate_id, tenant_id=candidate.tenant_id)
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

    async def list_cover_letter_versions(self, candidate_id: str, auth: AuthContext) -> list[CoverLetterVersionResponse]:
        candidate = await self._repo.get_candidate(candidate_id, tenant_id=auth.tenant_id if auth.enforced else None)
        ensure_tenant_access(auth, candidate.tenant_id)
        rows = await self._repo.list_cover_letter_versions(candidate_id, tenant_id=candidate.tenant_id)
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
