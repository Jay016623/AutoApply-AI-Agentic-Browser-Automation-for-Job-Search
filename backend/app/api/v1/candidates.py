"""Candidate API routes."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, get_db
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
    auth: AuthContext = Depends(get_auth_context),
    tenant_id: str | None = Query(default=None),
) -> CandidateListResponse:
    """List candidates, optionally scoped by tenant."""
    service = CandidateService(db)
    return await service.list_candidates(auth=auth, tenant_id=tenant_id)


@router.post("/", response_model=CandidateResponse, status_code=201, summary="Create candidate")
async def create_candidate(
    payload: CandidateCreate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateResponse:
    """Create a candidate record."""
    service = CandidateService(db)
    return await service.create_candidate(payload, auth=auth)


@router.get("/{candidate_id}", response_model=CandidateResponse, summary="Get candidate")
async def get_candidate(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateResponse:
    service = CandidateService(db)
    return await service.get_candidate(candidate_id, auth=auth)


@router.put("/{candidate_id}", response_model=CandidateResponse, summary="Update candidate")
async def update_candidate(
    candidate_id: str,
    payload: CandidateUpdate,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateResponse:
    service = CandidateService(db)
    return await service.update_candidate(candidate_id, payload, auth=auth)


@router.get("/{candidate_id}/settings", response_model=CandidateSettingsSchema, summary="Get candidate settings")
async def get_candidate_settings(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateSettingsSchema:
    service = CandidateService(db)
    return await service.get_candidate_settings(candidate_id, auth=auth)


@router.put("/{candidate_id}/settings", response_model=CandidateSettingsSchema, summary="Update candidate settings")
async def update_candidate_settings(
    candidate_id: str,
    settings: CandidateSettingsSchema,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateSettingsSchema:
    service = CandidateService(db)
    return await service.update_candidate_settings(candidate_id, settings, auth=auth)


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
    auth: AuthContext = Depends(get_auth_context),
) -> CandidateProfileSnapshotResponse:
    service = CandidateService(db)
    return await service.create_profile_snapshot(candidate_id, payload, auth=auth)


@router.get(
    "/{candidate_id}/profile-snapshots",
    response_model=list[CandidateProfileSnapshotResponse],
    summary="List profile snapshots",
)
async def list_profile_snapshots(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[CandidateProfileSnapshotResponse]:
    service = CandidateService(db)
    return await service.list_profile_snapshots(candidate_id, auth=auth)


@router.get(
    "/{candidate_id}/resume-versions",
    response_model=list[ResumeVersionResponse],
    summary="List resume versions",
)
async def list_resume_versions(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[ResumeVersionResponse]:
    service = CandidateService(db)
    return await service.list_resume_versions(candidate_id, auth=auth)


@router.get(
    "/{candidate_id}/cover-letter-versions",
    response_model=list[CoverLetterVersionResponse],
    summary="List cover letter versions",
)
async def list_cover_letter_versions(
    candidate_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[CoverLetterVersionResponse]:
    service = CandidateService(db)
    return await service.list_cover_letter_versions(candidate_id, auth=auth)
