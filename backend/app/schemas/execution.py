"""Schemas for execution visibility APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ExecutionAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    application_id: str
    workflow_run_id: str | None = None
    candidate_id: str | None = None
    job_id: str | None = None
    status: str
    current_step: str | None = None
    attempt_number: int
    retry_count: int
    risk_score: float
    confidence_score: float
    risk_level: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None
    manual_checkpoint_required: bool
    manual_checkpoint_reason: str | None = None
    created_at: datetime
    updated_at: datetime


class ExecutionAttemptListResponse(BaseModel):
    items: list[ExecutionAttemptResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ExecutionStepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    attempt_id: str
    step_name: str
    sequence_number: int
    status: str
    started_at: datetime | None = None
    completed_at: datetime | None = None
    retryable: bool
    retry_count: int
    error_code: str | None = None
    error_message: str | None = None
    input_snapshot_json: dict | None = None
    output_snapshot_json: dict | None = None
    idempotency_key: str
    created_at: datetime
    updated_at: datetime


class ProofArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tenant_id: str | None = None
    application_id: str | None = None
    workflow_run_id: str | None = None
    attempt_id: str | None = None
    attempt_step_id: str | None = None
    artifact_type: str
    storage_path: str
    checksum: str | None = None
    storage_backend: str
    object_key: str | None = None
    bucket_name: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    metadata_json: dict | None = None
    temporary_download_url: str | None = None
    created_at: datetime
    updated_at: datetime


class ProofArtifactListResponse(BaseModel):
    items: list[ProofArtifactResponse]
    total: int
    page: int
    page_size: int
    has_next: bool


class ArtifactDownloadUrlResponse(BaseModel):
    artifact_id: str
    expires_in_seconds: int
    url: str


class TimelineEventResponse(BaseModel):
    event_id: str
    category: str
    event_type: str
    occurred_at: datetime
    tenant_id: str | None = None
    application_id: str | None = None
    workflow_run_id: str | None = None
    attempt_id: str | None = None
    trace_id: str | None = None
    actor_id: str | None = None
    actor_type: str | None = None
    state_from: str | None = None
    state_to: str | None = None
    failure_classification: str | None = None
    artifact_id: str | None = None
    artifact_type: str | None = None
    status: str | None = None
    message: str | None = None
    payload: dict | None = None


class TimelineResponse(BaseModel):
    items: list[TimelineEventResponse]
