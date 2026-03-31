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
