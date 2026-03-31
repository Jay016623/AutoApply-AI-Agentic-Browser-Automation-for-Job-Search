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
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class ProofArtifactListResponse(BaseModel):
    items: list[ProofArtifactResponse]
    total: int
    page: int
    page_size: int
    has_next: bool
