"""Minimal auth/rbac context and tenant enforcement helpers."""

from dataclasses import dataclass
from enum import StrEnum

from fastapi import HTTPException, status


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    RECRUITER = "recruiter"
    REVIEWER = "reviewer"
    OPERATOR = "operator"
    READ_ONLY = "read_only"


@dataclass(frozen=True)
class AuthContext:
    user_id: str | None
    tenant_id: str | None
    role: Role | None
    enforced: bool


def require_tenant(ctx: AuthContext) -> str:
    if ctx.tenant_id:
        return ctx.tenant_id
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_id_required")


def ensure_tenant_access(ctx: AuthContext, resource_tenant_id: str | None) -> None:
    if not ctx.enforced:
        return
    if ctx.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_tenant_context")
    if resource_tenant_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="resource_not_tenant_scoped")
    if ctx.tenant_id != resource_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="cross_tenant_access_denied")


def ensure_role(ctx: AuthContext, allowed: set[Role]) -> None:
    if not ctx.enforced:
        return
    if ctx.role is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing_role_context")
    if ctx.role not in allowed:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="insufficient_role")
