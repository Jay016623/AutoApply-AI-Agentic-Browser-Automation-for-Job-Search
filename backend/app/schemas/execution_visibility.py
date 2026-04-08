"""Schemas for execution visibility operational APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ApplicationAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    application_id: str
    candidate_id: str | None = None
    status: str
    trigger_reason: str | None = None
    execution_task_id: str | None = None
    worker_trace_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    failed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class ApplicationAttemptStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    attempt_id: str
    application_id: str
    step_name: str
    step_order: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ProofArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    application_id: str
    attempt_id: str
    step_id: str | None = None
    artifact_type: str
    storage_uri: str
    content_type: str | None = None
    checksum: str | None = None
    captured_at: datetime | None = None
    metadata_json: dict | None = None
    created_at: datetime


class ManualCheckpointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str
    application_id: str
    attempt_id: str
    step_id: str | None = None
    checkpoint_type: str
    status: str
    reason_code: str
    reason_message: str
    blocker_confidence: str | None = None
    assigned_to: str | None = None
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_note: str | None = None
