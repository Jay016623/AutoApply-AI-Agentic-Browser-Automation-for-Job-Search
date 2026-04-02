"""Schemas for review queue and manual actions."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReviewTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    application_id: str | None = None
    workflow_run_id: str
    attempt_id: str | None = None
    reason: str
    status: str
    risk_level: str | None = None
    details_json: dict | None = None
    resolution_action: str | None = None
    resolution_notes: str | None = None
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class ReviewTaskListResponse(BaseModel):
    items: list[ReviewTaskResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ReviewActionRequest(BaseModel):
    action: str
    notes: str | None = None


class ReviewTaskCreate(BaseModel):
    tenant_id: str
    application_id: str | None = None
    workflow_run_id: str
    attempt_id: str | None = None
    reason: str
    risk_level: str | None = None
    details_json: dict | None = None
    idempotency_key: str
