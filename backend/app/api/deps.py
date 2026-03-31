"""Shared FastAPI dependencies for route injection."""

from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthContext, Role
from app.config.settings import get_settings
from app.db.redis import get_redis as _get_redis
from app.db.session import get_db as _get_db
from app.models.tenant_membership import TenantMembership


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


async def get_auth_context(
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_role: str | None = Header(default=None, alias="X-Role"),
) -> AuthContext:
    """Resolve auth context with feature-flagged hard tenant enforcement."""
    settings = get_settings()
    enforced = settings.feature_flags.tenant_enforcement

    role: Role | None = None
    if x_role:
        try:
            role = Role(x_role)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_role_header") from None

    if not enforced:
        return AuthContext(user_id=x_user_id, tenant_id=x_tenant_id, role=role, enforced=False)

    if not x_user_id or not x_tenant_id or role is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="hard_tenant_enforcement_requires_user_tenant_role",
        )

    result = await db.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == x_user_id,
            TenantMembership.tenant_id == x_tenant_id,
        ),
    )
    membership = result.scalar_one_or_none()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="tenant_membership_required")
    if membership.role != role.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="role_mismatch_with_membership")

    return AuthContext(user_id=x_user_id, tenant_id=x_tenant_id, role=role, enforced=True)
