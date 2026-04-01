"""Tenant-scoped read surfaces for execution visibility."""

from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE
from app.config.settings import get_settings
from app.core.auth import AuthContext, Role, ensure_role, require_tenant
from app.core.exceptions import RecordNotFoundError
from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.proof_artifact import ProofArtifact
from app.services.artifacts import get_artifact_storage
from app.schemas.execution import (
    ArtifactDownloadUrlResponse,
    ExecutionAttemptListResponse,
    ExecutionAttemptResponse,
    ExecutionStepResponse,
    ProofArtifactListResponse,
    ProofArtifactResponse,
)

_READ_ROLES = {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.RECRUITER, Role.REVIEWER, Role.READ_ONLY}


def _attempt_filters(
    auth: AuthContext,
    status: str | None,
    candidate_id: str | None,
    application_id: str | None,
    created_after: datetime | None,
    created_before: datetime | None,
):
    filters = []
    if auth.enforced:
        filters.append(ApplicationAttempt.tenant_id == require_tenant(auth))
    elif auth.tenant_id:
        filters.append(ApplicationAttempt.tenant_id == auth.tenant_id)
    if status:
        filters.append(ApplicationAttempt.status == status)
    if candidate_id:
        filters.append(ApplicationAttempt.candidate_id == candidate_id)
    if application_id:
        filters.append(ApplicationAttempt.application_id == application_id)
    if created_after:
        filters.append(ApplicationAttempt.created_at >= created_after)
    if created_before:
        filters.append(ApplicationAttempt.created_at <= created_before)
    return filters


async def list_attempts(
    db: AsyncSession,
    auth: AuthContext,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    status: str | None = None,
    candidate_id: str | None = None,
    application_id: str | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
) -> ExecutionAttemptListResponse:
    ensure_role(auth, _READ_ROLES)
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    filters = _attempt_filters(auth, status, candidate_id, application_id, created_after, created_before)
    query = select(ApplicationAttempt).where(and_(*filters)) if filters else select(ApplicationAttempt)
    count_query = select(func.count(ApplicationAttempt.id)).where(and_(*filters)) if filters else select(func.count(ApplicationAttempt.id))

    result = await db.execute(query.order_by(ApplicationAttempt.created_at.desc()).offset(offset).limit(page_size))
    rows = list(result.scalars().all())
    total = int((await db.execute(count_query)).scalar() or 0)

    return ExecutionAttemptListResponse(
        items=[ExecutionAttemptResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


async def get_attempt(db: AsyncSession, auth: AuthContext, attempt_id: str) -> ExecutionAttemptResponse:
    ensure_role(auth, _READ_ROLES)
    query = select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id)
    if auth.enforced:
        query = query.where(ApplicationAttempt.tenant_id == require_tenant(auth))
    elif auth.tenant_id:
        query = query.where(ApplicationAttempt.tenant_id == auth.tenant_id)
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError("ApplicationAttempt", attempt_id)
    return ExecutionAttemptResponse.model_validate(row)


async def list_attempt_steps(db: AsyncSession, auth: AuthContext, attempt_id: str) -> list[ExecutionStepResponse]:
    _ = await get_attempt(db, auth, attempt_id)
    query = select(ApplicationAttemptStep).where(ApplicationAttemptStep.attempt_id == attempt_id)
    if auth.enforced:
        query = query.where(ApplicationAttemptStep.tenant_id == require_tenant(auth))
    elif auth.tenant_id:
        query = query.where(ApplicationAttemptStep.tenant_id == auth.tenant_id)
    result = await db.execute(query.order_by(ApplicationAttemptStep.sequence_number.asc()))
    return [ExecutionStepResponse.model_validate(r) for r in result.scalars().all()]


async def list_attempt_artifacts(
    db: AsyncSession,
    auth: AuthContext,
    attempt_id: str,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    artifact_type: str | None = None,
    attempt_step_id: str | None = None,
) -> ProofArtifactListResponse:
    _ = await get_attempt(db, auth, attempt_id)
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    query = select(ProofArtifact).where(ProofArtifact.attempt_id == attempt_id)
    count_query = select(func.count(ProofArtifact.id)).where(ProofArtifact.attempt_id == attempt_id)
    if artifact_type:
        query = query.where(ProofArtifact.artifact_type == artifact_type)
        count_query = count_query.where(ProofArtifact.artifact_type == artifact_type)
    if attempt_step_id:
        query = query.where(ProofArtifact.attempt_step_id == attempt_step_id)
        count_query = count_query.where(ProofArtifact.attempt_step_id == attempt_step_id)
    if auth.enforced:
        tenant_id = require_tenant(auth)
        query = query.where(ProofArtifact.tenant_id == tenant_id)
        count_query = count_query.where(ProofArtifact.tenant_id == tenant_id)
    elif auth.tenant_id:
        query = query.where(ProofArtifact.tenant_id == auth.tenant_id)
        count_query = count_query.where(ProofArtifact.tenant_id == auth.tenant_id)

    rows = (await db.execute(query.order_by(ProofArtifact.created_at.desc()).offset(offset).limit(page_size))).scalars().all()
    total = int((await db.execute(count_query)).scalar() or 0)
    return ProofArtifactListResponse(
        items=[ProofArtifactResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


async def get_artifact_download_url(db: AsyncSession, auth: AuthContext, artifact_id: str) -> ArtifactDownloadUrlResponse:
    ensure_role(auth, _READ_ROLES)
    query = select(ProofArtifact).where(ProofArtifact.id == artifact_id)
    if auth.enforced:
        query = query.where(ProofArtifact.tenant_id == require_tenant(auth))
    elif auth.tenant_id:
        query = query.where(ProofArtifact.tenant_id == auth.tenant_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise RecordNotFoundError("ProofArtifact", artifact_id)

    settings = get_settings()
    storage = get_artifact_storage()
    expires = settings.artifact_storage_presign_ttl_seconds
    url = await storage.get_temporary_download_url(
        storage_path=row.storage_path,
        object_key=row.object_key,
        expires_in_seconds=expires,
    )
    return ArtifactDownloadUrlResponse(artifact_id=row.id, expires_in_seconds=expires, url=url)


async def list_manual_queue(
    db: AsyncSession,
    auth: AuthContext,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ExecutionAttemptListResponse:
    return await list_attempts(db, auth, page=page, page_size=page_size, status="waiting_manual")


async def list_retry_queue(
    db: AsyncSession,
    auth: AuthContext,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> ExecutionAttemptListResponse:
    ensure_role(auth, _READ_ROLES)
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    query = select(ApplicationAttempt).where(
        ApplicationAttempt.status.in_(["failed_retryable", "retry_scheduled"]),
    )
    count_query = select(func.count(ApplicationAttempt.id)).where(
        ApplicationAttempt.status.in_(["failed_retryable", "retry_scheduled"]),
    )
    if auth.enforced:
        tenant_id = require_tenant(auth)
        query = query.where(ApplicationAttempt.tenant_id == tenant_id)
        count_query = count_query.where(ApplicationAttempt.tenant_id == tenant_id)
    elif auth.tenant_id:
        query = query.where(ApplicationAttempt.tenant_id == auth.tenant_id)
        count_query = count_query.where(ApplicationAttempt.tenant_id == auth.tenant_id)

    rows = (await db.execute(query.order_by(ApplicationAttempt.updated_at.desc()).offset(offset).limit(page_size))).scalars().all()
    total = int((await db.execute(count_query)).scalar() or 0)
    return ExecutionAttemptListResponse(
        items=[ExecutionAttemptResponse.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )
