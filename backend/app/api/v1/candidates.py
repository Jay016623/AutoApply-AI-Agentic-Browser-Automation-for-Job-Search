"""Candidate API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantContext, get_db, get_tenant_context
from app.domains.candidate.service import CandidateService
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

router = APIRouter()


@router.get("/", response_model=CandidateListResponse, summary="List candidates")
async def list_candidates(
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    tenant_id: str | None = Query(default=None),
) -> CandidateListResponse:
    """List candidates, optionally scoped by tenant."""
    service = CandidateService(db)
    scope_tenant = tenant_id or tenant_ctx.tenant_id
    return await service.list_candidates(tenant_id=scope_tenant)


@router.post("/", response_model=CandidateResponse, status_code=201, summary="Create candidate")
async def create_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> CandidateResponse:
    """Create a candidate record."""
    service = CandidateService(db)
    if payload.tenant_id is None and tenant_ctx.tenant_id:
        payload = payload.model_copy(update={"tenant_id": tenant_ctx.tenant_id})
    return await service.create_candidate(payload)


@router.get("/{candidate_id}", response_model=CandidateResponse, summary="Get candidate")
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
) -> CandidateResponse:
    service = CandidateService(db)
    return await service.get_candidate(candidate_id)


@router.put("/{candidate_id}", response_model=CandidateResponse, summary="Update candidate")
async def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
) -> CandidateResponse:
    service = CandidateService(db)
    return await service.update_candidate(candidate_id, payload)


@router.get("/{candidate_id}/settings", response_model=CandidateSettingsSchema, summary="Get candidate settings")
async def get_candidate_settings(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
) -> CandidateSettingsSchema:
    service = CandidateService(db)
    return await service.get_candidate_settings(candidate_id)


@router.put("/{candidate_id}/settings", response_model=CandidateSettingsSchema, summary="Update candidate settings")
async def update_candidate_settings(
    candidate_id: str,
    settings: CandidateSettingsSchema,
    db: AsyncSession = Depends(get_db),
) -> CandidateSettingsSchema:
    service = CandidateService(db)
    return await service.update_candidate_settings(candidate_id, settings)


@router.post(
    "/{candidate_id}/profile-snapshots",
    response_model=CandidateProfileSnapshotResponse,
    status_code=201,
    summary="Create profile snapshot",
)
async def create_profile_snapshot(
    candidate_id: str,
    payload: CandidateProfileSnapshotCreate,
    db: AsyncSession = Depends(get_db),
) -> CandidateProfileSnapshotResponse:
    service = CandidateService(db)
    return await service.create_profile_snapshot(candidate_id, payload)


@router.get(
    "/{candidate_id}/profile-snapshots",
    response_model=list[CandidateProfileSnapshotResponse],
    summary="List profile snapshots",
)
async def list_profile_snapshots(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[CandidateProfileSnapshotResponse]:
    service = CandidateService(db)
    return await service.list_profile_snapshots(candidate_id)


@router.get(
    "/{candidate_id}/resume-versions",
    response_model=list[ResumeVersionResponse],
    summary="List resume versions",
)
async def list_resume_versions(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[ResumeVersionResponse]:
    service = CandidateService(db)
    return await service.list_resume_versions(candidate_id)


@router.get(
    "/{candidate_id}/cover-letter-versions",
    response_model=list[CoverLetterVersionResponse],
    summary="List cover letter versions",
)
async def list_cover_letter_versions(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
) -> list[CoverLetterVersionResponse]:
    service = CandidateService(db)
    return await service.list_cover_letter_versions(candidate_id)
