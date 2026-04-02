"""Schemas for operational admin endpoints."""

from pydantic import BaseModel


class SystemHealthResponse(BaseModel):
    """Operational system health summary."""

    api: str
    redis: str
    workflow_v2_enabled: bool
    tenant_enforcement: bool


class DependencyStatusResponse(BaseModel):
    status: str
    latency_ms: float
    details: str | None = None


class ReadinessResponse(BaseModel):
    status: str
    api: str
    database: DependencyStatusResponse
    redis: DependencyStatusResponse
    artifact_storage: DependencyStatusResponse
    queues: dict[str, int]


class QueueDepthResponse(BaseModel):
    """Queue depths for worker operations."""

    apply: int
    apply_dead_letter: int = 0
    scrape: int
    generate: int


class OpsDiagnosticsResponse(BaseModel):
    queue_depths: dict[str, int]
    workflow_pressure: dict[str, int]
    tenant_enforcement: bool
    strict_startup_validation: bool


class TenantPlanUpdateRequest(BaseModel):
    plan_key: str
    plan_overrides: dict | None = None
    feature_overrides: dict | None = None


class TenantControlPlaneStatusResponse(BaseModel):
    tenant_id: str
    plan_key: str
    features: dict[str, bool]
    quotas: dict[str, dict[str, float | bool]]


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
