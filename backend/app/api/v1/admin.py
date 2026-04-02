"""Operational admin endpoints for health, diagnostics, and session bootstrap."""

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_auth_context, get_db, get_redis
from app.core.auth import Role, ensure_role
from app.core.principal import issue_principal_token
from app.config.constants import QUEUE_APPLY, QUEUE_APPLY_DEAD_LETTER, QUEUE_GENERATE, QUEUE_SCRAPE
from app.config.settings import get_settings
from app.db.redis import is_redis_available
from app.models.tenant_membership import TenantMembership
from app.schemas.admin import (
    DependencyStatusResponse,
    OpsDiagnosticsResponse,
    QueueDepthResponse,
    ReadinessResponse,
    SessionBootstrapRequest,
    SessionBootstrapResponse,
    SystemHealthResponse,
    TenantControlPlaneStatusResponse,
    TenantPlanUpdateRequest,
)
from app.services import control_plane, ops_diagnostics
from app.services.queue import get_queue_depth

router = APIRouter()


@router.get("/health", response_model=SystemHealthResponse, summary="Operational health")
async def system_health(
    auth: AuthContext = Depends(get_auth_context),
) -> SystemHealthResponse:
    """Return operational status used by admin tooling."""
    ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.READ_ONLY})
    settings = get_settings()
    redis_ok = await is_redis_available()
    return SystemHealthResponse(
        api="ok",
        redis="ok" if redis_ok else "degraded",
        workflow_v2_enabled=settings.feature_flags.workflow_v2_enabled,
        tenant_enforcement=settings.feature_flags.tenant_enforcement,
    )


@router.get("/ready", response_model=ReadinessResponse, summary="Readiness checks")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    auth: AuthContext = Depends(get_auth_context),
) -> ReadinessResponse:
    """Run dependency readiness checks for API, DB, Redis, queues, and artifacts."""
    ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.READ_ONLY})
    database = await ops_diagnostics.check_database(db)
    redis_status = await ops_diagnostics.check_redis(redis)
    artifact = await ops_diagnostics.check_artifact_backend()
    queues = await ops_diagnostics.queue_depth_snapshot(redis)
    overall_ok = all(item.status == "ok" for item in (database, redis_status, artifact))
    if not overall_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if overall_ok else "degraded",
        api="ok",
        database=DependencyStatusResponse(
            status=database.status,
            latency_ms=database.latency_ms,
            details=database.details or None,
        ),
        redis=DependencyStatusResponse(
            status=redis_status.status,
            latency_ms=redis_status.latency_ms,
            details=redis_status.details or None,
        ),
        artifact_storage=DependencyStatusResponse(
            status=artifact.status,
            latency_ms=artifact.latency_ms,
            details=artifact.details or None,
        ),
        queues=queues,
    )


@router.get("/queues", response_model=QueueDepthResponse, summary="Queue depths")
async def queue_depths(
    redis=Depends(get_redis),
    auth: AuthContext = Depends(get_auth_context),
) -> QueueDepthResponse:
    """Return queue backlog depths for operational visibility."""
    ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.OPERATOR})
    if redis is None:
        return QueueDepthResponse(apply=0, apply_dead_letter=0, scrape=0, generate=0)

    apply_depth = await get_queue_depth(redis, QUEUE_APPLY)
    apply_dead_letter_depth = await get_queue_depth(redis, QUEUE_APPLY_DEAD_LETTER)
    scrape_depth = await get_queue_depth(redis, QUEUE_SCRAPE)
    generate_depth = await get_queue_depth(redis, QUEUE_GENERATE)

    return QueueDepthResponse(
        apply=apply_depth,
        apply_dead_letter=apply_dead_letter_depth,
        scrape=scrape_depth,
        generate=generate_depth,
    )


@router.get("/diagnostics", response_model=OpsDiagnosticsResponse, summary="Operations diagnostics")
async def diagnostics(
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
    auth: AuthContext = Depends(get_auth_context),
) -> OpsDiagnosticsResponse:
    """Return queue and workflow pressure diagnostics for incident response."""
    ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.READ_ONLY})
    if auth.tenant_id:
        try:
            await control_plane.require_feature(
                db,
                tenant_id=auth.tenant_id,
                feature_key="advanced_execution_diagnostics",
                actor_id=auth.user_id,
            )
        except control_plane.QuotaExceededError as exc:
            raise HTTPException(status_code=402, detail=str(exc)) from exc
    settings = get_settings()
    return OpsDiagnosticsResponse(
        queue_depths=await ops_diagnostics.queue_depth_snapshot(redis),
        workflow_pressure=await ops_diagnostics.workflow_pressure_snapshot(db),
        tenant_enforcement=settings.strict_tenant_enforcement,
        strict_startup_validation=settings.feature_flags.strict_tenant_startup_validation,
    )


@router.get("/control/plan", response_model=TenantControlPlaneStatusResponse, summary="Current tenant plan + quota status")
async def current_tenant_plan_status(
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TenantControlPlaneStatusResponse:
    """Return plan, feature flags, and quota usage for the authenticated tenant."""
    ensure_role(auth, {Role.OWNER, Role.ADMIN, Role.OPERATOR, Role.READ_ONLY, Role.RECRUITER})
    status_payload = await control_plane.get_current_tenant_quota_status(db, auth)
    return TenantControlPlaneStatusResponse.model_validate(status_payload)


@router.put("/control/tenants/{tenant_id}/plan", response_model=TenantControlPlaneStatusResponse, summary="Update tenant plan")
async def update_tenant_plan(
    tenant_id: str,
    payload: TenantPlanUpdateRequest,
    db: AsyncSession = Depends(get_db),
    auth: AuthContext = Depends(get_auth_context),
) -> TenantControlPlaneStatusResponse:
    """Update plan key and optional override maps for a tenant (owner/admin only)."""
    await control_plane.update_tenant_plan(
        db,
        tenant_id=tenant_id,
        plan_key=payload.plan_key,
        plan_overrides=payload.plan_overrides,
        feature_overrides=payload.feature_overrides,
        auth=auth,
    )
    status_payload = await control_plane.get_tenant_quota_status(db, tenant_id)
    return TenantControlPlaneStatusResponse.model_validate(status_payload)


@router.post("/session/bootstrap", response_model=SessionBootstrapResponse, summary="Bootstrap session token")
async def session_bootstrap(
    payload: SessionBootstrapRequest,
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> SessionBootstrapResponse:
    """Mint a signed principal token from validated tenant membership.

    This endpoint is an incremental bridge until external IdP auth is integrated.
    It can be disabled by setting AUTH__ALLOW_LEGACY_HEADER_AUTH=false.
    """
    settings = get_settings()
    if not settings.auth.allow_legacy_header_auth:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="session_bootstrap_disabled")
    if not x_user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="x_user_id_required_for_bootstrap")

    try:
        requested_role = Role(payload.role)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_role") from exc

    membership = (
        await db.execute(
            select(TenantMembership).where(
                TenantMembership.user_id == x_user_id,
                TenantMembership.tenant_id == payload.tenant_id,
            ),
        )
    ).scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant_membership_required")
    if membership.role != requested_role.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_mismatch_with_membership")

    expires_in = settings.auth.token_ttl_seconds
    token = issue_principal_token(
        user_id=x_user_id,
        tenant_id=payload.tenant_id,
        role=requested_role,
        secret=settings.auth.token_secret.get_secret_value(),
        ttl_seconds=expires_in,
    )
    return SessionBootstrapResponse(
        access_token=token,
        expires_in=expires_in,
        user_id=x_user_id,
        tenant_id=payload.tenant_id,
        role=requested_role.value,
    )
