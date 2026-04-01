"""Execution visibility endpoints for operators."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, get_db
from app.config.constants import DEFAULT_PAGE_SIZE
from app.schemas.execution import (
    ExecutionAttemptListResponse,
    ExecutionAttemptResponse,
    ExecutionStepResponse,
    ProofArtifactListResponse,
    ArtifactDownloadUrlResponse,
    TimelineResponse,
)
from app.services import execution_query as execution_service
from app.services import timeline_query

router = APIRouter()


@router.get("/attempts", response_model=ExecutionAttemptListResponse)
async def list_attempts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    status: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
    application_id: str | None = Query(default=None),
    created_after: datetime | None = Query(default=None),
    created_before: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ExecutionAttemptListResponse:
    return await execution_service.list_attempts(
        db,
        auth,
        page=page,
        page_size=page_size,
        status=status,
        candidate_id=candidate_id,
        application_id=application_id,
        created_after=created_after,
        created_before=created_before,
    )


@router.get("/attempts/{attempt_id}", response_model=ExecutionAttemptResponse)
async def get_attempt(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ExecutionAttemptResponse:
    return await execution_service.get_attempt(db, auth, attempt_id)


@router.get("/attempts/{attempt_id}/steps", response_model=list[ExecutionStepResponse])
async def list_attempt_steps(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> list[ExecutionStepResponse]:
    return await execution_service.list_attempt_steps(db, auth, attempt_id)


@router.get("/attempts/{attempt_id}/artifacts", response_model=ProofArtifactListResponse)
async def list_artifacts(
    attempt_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    artifact_type: str | None = Query(default=None),
    attempt_step_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ProofArtifactListResponse:
    return await execution_service.list_attempt_artifacts(
        db,
        auth,
        attempt_id,
        page=page,
        page_size=page_size,
        artifact_type=artifact_type,
        attempt_step_id=attempt_step_id,
    )


@router.get("/manual-queue", response_model=ExecutionAttemptListResponse)
async def manual_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ExecutionAttemptListResponse:
    return await execution_service.list_manual_queue(db, auth, page=page, page_size=page_size)


@router.get("/retry-queue", response_model=ExecutionAttemptListResponse)
async def retry_queue(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ExecutionAttemptListResponse:
    return await execution_service.list_retry_queue(db, auth, page=page, page_size=page_size)


@router.get("/artifacts/{artifact_id}/download-url", response_model=ArtifactDownloadUrlResponse)
async def artifact_download_url(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> ArtifactDownloadUrlResponse:
    return await execution_service.get_artifact_download_url(db, auth, artifact_id)


@router.get("/timeline/execution", response_model=TimelineResponse)
async def execution_timeline(
    application_id: str | None = Query(default=None),
    workflow_run_id: str | None = Query(default=None),
    attempt_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TimelineResponse:
    return await timeline_query.execution_timeline(
        db,
        auth,
        application_id=application_id,
        workflow_run_id=workflow_run_id,
        attempt_id=attempt_id,
    )


@router.get("/timeline/audit", response_model=TimelineResponse)
async def audit_timeline(
    application_id: str | None = Query(default=None),
    workflow_run_id: str | None = Query(default=None),
    attempt_id: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TimelineResponse:
    return await timeline_query.audit_timeline(
        db,
        auth,
        application_id=application_id,
        workflow_run_id=workflow_run_id,
        attempt_id=attempt_id,
        limit=limit,
    )
