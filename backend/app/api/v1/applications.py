"""Application tracking API routes."""

from datetime import datetime

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    TenantContext,
    get_db,
    get_tenant_context,
    require_execution_write_tenant,
)
from app.config.constants import DEFAULT_PAGE_SIZE
from app.schemas.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
)
from app.schemas.execution_visibility import (
    ApplicationAttemptResponse,
    ApplicationAttemptStepResponse,
    ManualCheckpointResponse,
    ProofArtifactResponse,
)
from app.services import application as app_service
from app.services import execution_visibility as visibility_service

logger = structlog.get_logger(__name__)
router = APIRouter()


@router.post(
    "/",
    response_model=ApplicationResponse,
    status_code=201,
    summary="Create an application",
)
async def create_application(
    data: ApplicationCreate,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationResponse:
    """Create a single job application."""
    resolved_tenant = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    data = data.model_copy(update={"tenant_id": resolved_tenant})
    app = await app_service.create_application(db, data)
    return ApplicationResponse.model_validate(app)


@router.post(
    "/batch",
    response_model=list[ApplicationResponse],
    status_code=201,
    summary="Batch create applications",
)
async def batch_create(
    data: ApplicationBatchCreate,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[ApplicationResponse]:
    """Create multiple job applications at once."""
    resolved_tenant = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    data = data.model_copy(update={"tenant_id": resolved_tenant})
    apps = await app_service.create_batch(db, data)
    return [ApplicationResponse.model_validate(a) for a in apps]


@router.get(
    "/",
    response_model=ApplicationListResponse,
    summary="List applications",
)
async def list_applications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    status: str | None = Query(default=None),
    tenant_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationListResponse:
    """List applications with pagination and optional status filter."""
    scope_tenant = tenant_id or tenant_ctx.tenant_id
    return await app_service.list_applications(db, page, page_size, status, scope_tenant)


@router.get(
    "/attempts",
    response_model=list[ApplicationAttemptResponse],
    summary="List execution attempts",
)
async def list_attempts(
    application_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    candidate_id: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[ApplicationAttemptResponse]:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    attempts = await visibility_service.list_attempts(
        db,
        tenant_id=tenant_id,
        application_id=application_id,
        status=status,
        candidate_id=candidate_id,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    return [ApplicationAttemptResponse.model_validate(a) for a in attempts]


@router.get(
    "/attempts/{attempt_id}",
    response_model=ApplicationAttemptResponse,
    summary="Get execution attempt",
)
async def get_attempt(
    attempt_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationAttemptResponse:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    attempt = await visibility_service.get_attempt(
        db,
        tenant_id=tenant_id,
        attempt_id=attempt_id,
    )
    return ApplicationAttemptResponse.model_validate(attempt)


@router.get(
    "/attempt-steps",
    response_model=list[ApplicationAttemptStepResponse],
    summary="List execution attempt steps",
)
async def list_attempt_steps(
    application_id: str | None = Query(default=None),
    attempt_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[ApplicationAttemptStepResponse]:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    steps = await visibility_service.list_steps(
        db,
        tenant_id=tenant_id,
        application_id=application_id,
        attempt_id=attempt_id,
        status=status,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    return [ApplicationAttemptStepResponse.model_validate(s) for s in steps]


@router.get(
    "/attempt-steps/{step_id}",
    response_model=ApplicationAttemptStepResponse,
    summary="Get execution attempt step",
)
async def get_attempt_step(
    step_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationAttemptStepResponse:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    step = await visibility_service.get_step(
        db,
        tenant_id=tenant_id,
        step_id=step_id,
    )
    return ApplicationAttemptStepResponse.model_validate(step)


@router.get(
    "/proof-artifacts",
    response_model=list[ProofArtifactResponse],
    summary="List proof artifacts",
)
async def list_proof_artifacts(
    application_id: str | None = Query(default=None),
    attempt_id: str | None = Query(default=None),
    artifact_type: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[ProofArtifactResponse]:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    artifacts = await visibility_service.list_proof_artifacts(
        db,
        tenant_id=tenant_id,
        application_id=application_id,
        attempt_id=attempt_id,
        artifact_type=artifact_type,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    return [ProofArtifactResponse.model_validate(a) for a in artifacts]


@router.get(
    "/proof-artifacts/{artifact_id}",
    response_model=ProofArtifactResponse,
    summary="Get proof artifact",
)
async def get_proof_artifact(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ProofArtifactResponse:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    artifact = await visibility_service.get_proof_artifact(
        db,
        tenant_id=tenant_id,
        artifact_id=artifact_id,
    )
    return ProofArtifactResponse.model_validate(artifact)


@router.get(
    "/manual-checkpoints",
    response_model=list[ManualCheckpointResponse],
    summary="List manual checkpoints",
)
async def list_manual_checkpoints(
    application_id: str | None = Query(default=None),
    attempt_id: str | None = Query(default=None),
    checkpoint_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> list[ManualCheckpointResponse]:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    checkpoints = await visibility_service.list_manual_checkpoints(
        db,
        tenant_id=tenant_id,
        application_id=application_id,
        attempt_id=attempt_id,
        checkpoint_type=checkpoint_type,
        status=status,
        created_from=created_from,
        created_to=created_to,
        limit=limit,
    )
    return [ManualCheckpointResponse.model_validate(c) for c in checkpoints]


@router.get(
    "/manual-checkpoints/{checkpoint_id}",
    response_model=ManualCheckpointResponse,
    summary="Get manual checkpoint",
)
async def get_manual_checkpoint(
    checkpoint_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ManualCheckpointResponse:
    tenant_id = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    checkpoint = await visibility_service.get_manual_checkpoint(
        db,
        tenant_id=tenant_id,
        checkpoint_id=checkpoint_id,
    )
    return ManualCheckpointResponse.model_validate(checkpoint)


@router.get(
    "/{app_id}",
    response_model=ApplicationResponse,
    summary="Get a single application",
)
async def get_application(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationResponse:
    """Get a single application by ID. Returns 404 if not found."""
    app = await app_service.get_application(db, app_id, tenant_id=tenant_ctx.tenant_id)
    return ApplicationResponse.model_validate(app)


@router.put(
    "/{app_id}/approve",
    response_model=ApplicationResponse,
    summary="Approve a pending application",
)
async def approve_application(
    app_id: str,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationResponse:
    """Approve a pending application for automated submission."""
    scope_tenant = require_execution_write_tenant(tenant_ctx, tenant_ctx.tenant_id)
    app = await app_service.approve_application(db, app_id, tenant_id=scope_tenant)
    return ApplicationResponse.model_validate(app)


@router.put(
    "/{app_id}/status",
    response_model=ApplicationResponse,
    summary="Update application status",
)
async def update_status(
    app_id: str,
    update: ApplicationStatusUpdate,
    db: AsyncSession = Depends(get_db),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
) -> ApplicationResponse:
    """Update an application's status and optional notes."""
    app = await app_service.update_status(
        db, app_id, update, tenant_id=tenant_ctx.tenant_id,
    )
    return ApplicationResponse.model_validate(app)
