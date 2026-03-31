"""Shared FastAPI dependencies for route injection."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Header
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import get_settings
from app.db.redis import get_redis as _get_redis
from app.db.session import get_db as _get_db


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Database session dependency."""
    async for session in _get_db():
        yield session


def get_redis() -> Redis | None:
    """Redis client dependency. Returns None if Redis unavailable."""
    return _get_redis()


@dataclass(frozen=True)
class TenantContext:
    """Tenant context resolved from request headers.

    Phase 1 keeps this optional for backward compatibility.
    """

    tenant_id: str | None
    actor_id: str | None
    enforced: bool


async def get_tenant_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_actor_id: str | None = Header(default=None, alias="X-Actor-Id"),
) -> TenantContext:
    """Resolve tenant context without breaking existing clients.

    When FEATURE__TENANT_ENFORCEMENT is disabled, missing tenant headers
    are tolerated for incremental rollout.
    """
    settings = get_settings()
    enforced = settings.feature_flags.tenant_enforcement
    return TenantContext(
        tenant_id=x_tenant_id,
        actor_id=x_actor_id,
        enforced=enforced,
    )
