"""Operational admin endpoints for Phase 1 foundations."""

from fastapi import APIRouter, Depends

from app.api.deps import AuthContext, get_auth_context, get_redis
from app.core.auth import Role, ensure_role
from app.config.constants import QUEUE_APPLY, QUEUE_GENERATE, QUEUE_SCRAPE
from app.config.settings import get_settings
from app.db.redis import is_redis_available
from app.schemas.admin import QueueDepthResponse, SystemHealthResponse
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
        return QueueDepthResponse(apply=0, scrape=0, generate=0)

    apply_depth = await get_queue_depth(redis, QUEUE_APPLY)
    scrape_depth = await get_queue_depth(redis, QUEUE_SCRAPE)
    generate_depth = await get_queue_depth(redis, QUEUE_GENERATE)

    return QueueDepthResponse(
        apply=apply_depth,
        scrape=scrape_depth,
        generate=generate_depth,
    )
