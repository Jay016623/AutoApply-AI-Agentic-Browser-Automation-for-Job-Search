"""Schemas for operational admin endpoints."""

from pydantic import BaseModel


class SystemHealthResponse(BaseModel):
    """Operational system health summary."""

    api: str
    redis: str
    workflow_v2_enabled: bool
    tenant_enforcement: bool


class QueueDepthResponse(BaseModel):
    """Queue depths for worker operations."""

    apply: int
    scrape: int
    generate: int


class SessionBootstrapRequest(BaseModel):
    """Session bootstrap request used to mint a principal token."""

    tenant_id: str
    role: str


class SessionBootstrapResponse(BaseModel):
    """Token + principal details returned during bootstrap."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    tenant_id: str
    role: str
