"""Execution visibility service for attempts, steps, proofs, and checkpoints."""

from datetime import UTC, datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import RecordNotFoundError
from app.models.application_attempt import ApplicationAttempt
from app.models.application_attempt_step import ApplicationAttemptStep
from app.models.manual_checkpoint import ManualCheckpoint
from app.models.proof_artifact import ProofArtifact

ATTEMPT_STATUS_RUNNING = "running"
ATTEMPT_STATUS_SUCCEEDED = "succeeded"
ATTEMPT_STATUS_FAILED = "failed"
ATTEMPT_STATUS_INTERRUPTED = "interrupted"

STEP_STATUS_RUNNING = "running"
STEP_STATUS_SUCCEEDED = "succeeded"
STEP_STATUS_FAILED = "failed"

CHECKPOINT_STATUS_OPEN = "open"
CHECKPOINT_STATUS_RESOLVED = "resolved"


async def start_attempt(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str,
    candidate_id: str | None,
    trigger_reason: str | None,
    execution_task_id: str | None,
    worker_trace_id: str | None,
) -> ApplicationAttempt:
    attempt = ApplicationAttempt(
        tenant_id=tenant_id,
        application_id=application_id,
        candidate_id=candidate_id,
        status=ATTEMPT_STATUS_RUNNING,
        trigger_reason=trigger_reason,
        execution_task_id=execution_task_id,
        worker_trace_id=worker_trace_id,
        started_at=datetime.now(UTC),
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def finalize_attempt(
    db: AsyncSession,
    *,
    attempt_id: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> ApplicationAttempt:
    result = await db.execute(select(ApplicationAttempt).where(ApplicationAttempt.id == attempt_id))
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise RecordNotFoundError("ApplicationAttempt", attempt_id)
    attempt.status = status
    attempt.error_code = error_code
    attempt.error_message = error_message
    now = datetime.now(UTC)
    if status == ATTEMPT_STATUS_SUCCEEDED:
        attempt.completed_at = now
        attempt.failed_at = None
    elif status in {ATTEMPT_STATUS_FAILED, ATTEMPT_STATUS_INTERRUPTED}:
        attempt.failed_at = now
        if status == ATTEMPT_STATUS_INTERRUPTED:
            attempt.completed_at = now
    await db.commit()
    await db.refresh(attempt)
    return attempt


async def start_step(
    db: AsyncSession,
    *,
    tenant_id: str,
    attempt_id: str,
    application_id: str,
    step_name: str,
    step_order: int,
    metadata_json: dict | None = None,
) -> ApplicationAttemptStep:
    step = ApplicationAttemptStep(
        tenant_id=tenant_id,
        attempt_id=attempt_id,
        application_id=application_id,
        step_name=step_name,
        step_order=step_order,
        status=STEP_STATUS_RUNNING,
        started_at=datetime.now(UTC),
        metadata_json=metadata_json,
    )
    db.add(step)
    await db.commit()
    await db.refresh(step)
    return step


async def complete_step(
    db: AsyncSession,
    *,
    step_id: str,
    metadata_json: dict | None = None,
) -> ApplicationAttemptStep:
    result = await db.execute(select(ApplicationAttemptStep).where(ApplicationAttemptStep.id == step_id))
    step = result.scalar_one_or_none()
    if step is None:
        raise RecordNotFoundError("ApplicationAttemptStep", step_id)
    step.status = STEP_STATUS_SUCCEEDED
    step.completed_at = datetime.now(UTC)
    if metadata_json is not None:
        step.metadata_json = metadata_json
    await db.commit()
    await db.refresh(step)
    return step


async def fail_step(
    db: AsyncSession,
    *,
    step_id: str,
    error_code: str,
    error_message: str,
    metadata_json: dict | None = None,
) -> ApplicationAttemptStep:
    result = await db.execute(select(ApplicationAttemptStep).where(ApplicationAttemptStep.id == step_id))
    step = result.scalar_one_or_none()
    if step is None:
        raise RecordNotFoundError("ApplicationAttemptStep", step_id)
    step.status = STEP_STATUS_FAILED
    step.error_code = error_code
    step.error_message = error_message
    step.completed_at = datetime.now(UTC)
    if metadata_json is not None:
        step.metadata_json = metadata_json
    await db.commit()
    await db.refresh(step)
    return step


async def record_proof_artifact(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str,
    attempt_id: str,
    step_id: str | None,
    artifact_type: str,
    storage_uri: str,
    content_type: str | None = None,
    metadata_json: dict | None = None,
) -> ProofArtifact:
    artifact = ProofArtifact(
        tenant_id=tenant_id,
        application_id=application_id,
        attempt_id=attempt_id,
        step_id=step_id,
        artifact_type=artifact_type,
        storage_uri=storage_uri,
        content_type=content_type,
        metadata_json=metadata_json,
        captured_at=datetime.now(UTC),
    )
    db.add(artifact)
    await db.commit()
    await db.refresh(artifact)
    return artifact


async def create_manual_checkpoint(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str,
    attempt_id: str,
    step_id: str | None,
    checkpoint_type: str,
    reason_code: str,
    reason_message: str,
    blocker_confidence: str | None,
) -> ManualCheckpoint:
    checkpoint = ManualCheckpoint(
        tenant_id=tenant_id,
        application_id=application_id,
        attempt_id=attempt_id,
        step_id=step_id,
        checkpoint_type=checkpoint_type,
        status=CHECKPOINT_STATUS_OPEN,
        reason_code=reason_code,
        reason_message=reason_message,
        blocker_confidence=blocker_confidence,
    )
    db.add(checkpoint)
    await db.commit()
    await db.refresh(checkpoint)
    return checkpoint


def _apply_date_filter(model, query, created_from: datetime | None, created_to: datetime | None):
    if created_from is not None:
        query = query.where(model.created_at >= created_from)
    if created_to is not None:
        query = query.where(model.created_at <= created_to)
    return query


async def list_attempts(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str | None = None,
    status: str | None = None,
    candidate_id: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 100,
) -> list[ApplicationAttempt]:
    query = select(ApplicationAttempt).where(ApplicationAttempt.tenant_id == tenant_id)
    if application_id:
        query = query.where(ApplicationAttempt.application_id == application_id)
    if status:
        query = query.where(ApplicationAttempt.status == status)
    if candidate_id:
        query = query.where(ApplicationAttempt.candidate_id == candidate_id)
    query = _apply_date_filter(ApplicationAttempt, query, created_from, created_to)
    query = query.order_by(ApplicationAttempt.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_attempt(db: AsyncSession, *, tenant_id: str, attempt_id: str) -> ApplicationAttempt:
    result = await db.execute(
        select(ApplicationAttempt).where(
            and_(
                ApplicationAttempt.id == attempt_id,
                ApplicationAttempt.tenant_id == tenant_id,
            ),
        ),
    )
    attempt = result.scalar_one_or_none()
    if attempt is None:
        raise RecordNotFoundError("ApplicationAttempt", attempt_id)
    return attempt


async def list_steps(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str | None = None,
    attempt_id: str | None = None,
    status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 200,
) -> list[ApplicationAttemptStep]:
    query = select(ApplicationAttemptStep).where(ApplicationAttemptStep.tenant_id == tenant_id)
    if application_id:
        query = query.where(ApplicationAttemptStep.application_id == application_id)
    if attempt_id:
        query = query.where(ApplicationAttemptStep.attempt_id == attempt_id)
    if status:
        query = query.where(ApplicationAttemptStep.status == status)
    query = _apply_date_filter(ApplicationAttemptStep, query, created_from, created_to)
    query = query.order_by(ApplicationAttemptStep.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_step(db: AsyncSession, *, tenant_id: str, step_id: str) -> ApplicationAttemptStep:
    result = await db.execute(
        select(ApplicationAttemptStep).where(
            and_(
                ApplicationAttemptStep.id == step_id,
                ApplicationAttemptStep.tenant_id == tenant_id,
            ),
        ),
    )
    step = result.scalar_one_or_none()
    if step is None:
        raise RecordNotFoundError("ApplicationAttemptStep", step_id)
    return step


async def list_proof_artifacts(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str | None = None,
    attempt_id: str | None = None,
    artifact_type: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 200,
) -> list[ProofArtifact]:
    query = select(ProofArtifact).where(ProofArtifact.tenant_id == tenant_id)
    if application_id:
        query = query.where(ProofArtifact.application_id == application_id)
    if attempt_id:
        query = query.where(ProofArtifact.attempt_id == attempt_id)
    if artifact_type:
        query = query.where(ProofArtifact.artifact_type == artifact_type)
    query = _apply_date_filter(ProofArtifact, query, created_from, created_to)
    query = query.order_by(ProofArtifact.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_proof_artifact(
    db: AsyncSession,
    *,
    tenant_id: str,
    artifact_id: str,
) -> ProofArtifact:
    result = await db.execute(
        select(ProofArtifact).where(
            and_(
                ProofArtifact.id == artifact_id,
                ProofArtifact.tenant_id == tenant_id,
            ),
        ),
    )
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise RecordNotFoundError("ProofArtifact", artifact_id)
    return artifact


async def list_manual_checkpoints(
    db: AsyncSession,
    *,
    tenant_id: str,
    application_id: str | None = None,
    attempt_id: str | None = None,
    checkpoint_type: str | None = None,
    status: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    limit: int = 200,
) -> list[ManualCheckpoint]:
    query = select(ManualCheckpoint).where(ManualCheckpoint.tenant_id == tenant_id)
    if application_id:
        query = query.where(ManualCheckpoint.application_id == application_id)
    if attempt_id:
        query = query.where(ManualCheckpoint.attempt_id == attempt_id)
    if checkpoint_type:
        query = query.where(ManualCheckpoint.checkpoint_type == checkpoint_type)
    if status:
        query = query.where(ManualCheckpoint.status == status)
    query = _apply_date_filter(ManualCheckpoint, query, created_from, created_to)
    query = query.order_by(ManualCheckpoint.created_at.desc()).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


async def get_manual_checkpoint(
    db: AsyncSession,
    *,
    tenant_id: str,
    checkpoint_id: str,
) -> ManualCheckpoint:
    result = await db.execute(
        select(ManualCheckpoint).where(
            and_(
                ManualCheckpoint.id == checkpoint_id,
                ManualCheckpoint.tenant_id == tenant_id,
            ),
        ),
    )
    checkpoint = result.scalar_one_or_none()
    if checkpoint is None:
        raise RecordNotFoundError("ManualCheckpoint", checkpoint_id)
    return checkpoint
