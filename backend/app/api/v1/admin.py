"""Operational admin endpoints for Phase 1 foundations."""

from fastapi import APIRouter, Depends, Header, HTTPException, status
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
    QueueDepthResponse,
    SessionBootstrapRequest,
    SessionBootstrapResponse,
    SystemHealthResponse,
)
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
