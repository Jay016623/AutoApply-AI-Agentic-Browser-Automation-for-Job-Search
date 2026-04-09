"""Application management service.

Handles creating, listing, approving, and updating job applications.
"""

from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.constants import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    QUEUE_APPLY,
    ApplicationStatus,
)
from app.core.exceptions import RecordNotFoundError
from app.db.redis import get_redis
from app.models.job import Job
from app.models.application import Application
from app.models.resume import Resume
from app.schemas.application import (
    ApplicationBatchCreate,
    ApplicationCreate,
    ApplicationListResponse,
    ApplicationResponse,
    ApplicationStatusUpdate,
)
from app.services.queue import enqueue_idempotent

logger = structlog.get_logger(__name__)
EXECUTION_ENQUEUE_LOCK_TTL_SECONDS = 6 * 60 * 60


def _application_in_active_execution(app: Application) -> bool:
    """Return True when an application is already in or past active execution."""
    return app.status in {
        ApplicationStatus.QUEUED,
        ApplicationStatus.APPROVED,
        ApplicationStatus.APPLYING,
        ApplicationStatus.APPLIED,
    }


async def _resolve_tenant_for_application(
    db: AsyncSession,
    *,
    job_id: str,
    resume_id: str | None,
    requested_tenant_id: str | None,
) -> str | None:
    """Resolve the most reliable tenant id for a new application."""
    if requested_tenant_id:
        return requested_tenant_id

    tenant_from_resume: str | None = None
    if resume_id:
        resume_result = await db.execute(
            select(Resume).where(Resume.id == resume_id),
        )
        resume = resume_result.scalar_one_or_none()
        if resume is not None:
            tenant_from_resume = resume.tenant_id

    job_result = await db.execute(select(Job).where(Job.id == job_id))
    job = job_result.scalar_one_or_none()
    tenant_from_job = job.tenant_id if job else None

    return tenant_from_resume or tenant_from_job


async def _enqueue_application_execution(
    db: AsyncSession,
    app: Application,
    *,
    reason: str,
) -> str | None:
    """Enqueue application execution when allowed and not already active."""
    if _application_in_active_execution(app) and app.execution_task_id:
        logger.info(
            "application_enqueue_skipped_existing_task",
            app_id=app.id,
            task_id=app.execution_task_id,
            status=app.status,
        )
        return None

    if app.status in {ApplicationStatus.APPLYING, ApplicationStatus.APPLIED}:
        logger.info(
            "application_enqueue_skipped_terminal",
            app_id=app.id,
            status=app.status,
        )
        return None

    if not app.tenant_id:
        logger.warning(
            "application_enqueue_blocked_missing_tenant",
            app_id=app.id,
            reason=reason,
        )
        raise ValueError("Tenant context is required for execution-producing writes.")

    redis = get_redis()
    if redis is None:
        logger.warning("application_enqueue_skipped_redis_unavailable", app_id=app.id)
        return None

    job_result = await db.execute(select(Job).where(Job.id == app.job_id))
    job = job_result.scalar_one_or_none()
    platform = job.platform if job else ""

    payload = {
        "application_id": app.id,
        "job_id": app.job_id,
        "resume_id": app.resume_id or "",
        "platform": platform,
        "tenant_id": app.tenant_id,
        "execution_anchor": app.id,
        "retry_count": 0,
        "enqueue_reason": reason,
    }
    idempotency_key = f"application:{app.id}:reason:{reason}"
    task_id, enqueued_now = await enqueue_idempotent(
        redis,
        QUEUE_APPLY,
        payload,
        idempotency_key=idempotency_key,
        lock_ttl_seconds=EXECUTION_ENQUEUE_LOCK_TTL_SECONDS,
    )
    app.execution_task_id = task_id
    if app.status == ApplicationStatus.APPROVED:
        app.status = ApplicationStatus.QUEUED
    await db.commit()
    await db.refresh(app)
    logger.info(
        "application_enqueued",
        app_id=app.id,
        task_id=task_id,
        reason=reason,
        enqueued_now=enqueued_now,
        idempotency_key=idempotency_key,
    )
    return task_id


async def create_application(
    db: AsyncSession,
    data: ApplicationCreate,
) -> Application:
    """Create a single job application.

    Args:
        db: Async database session.
        data: Application creation data.

    Returns:
        The newly created Application.
    """
    tenant_id = await _resolve_tenant_for_application(
        db,
        job_id=data.job_id,
        resume_id=data.resume_id,
        requested_tenant_id=data.tenant_id,
    )
    if data.apply_mode == "autonomous" and not tenant_id:
        raise ValueError(
            "Tenant context is required for autonomous execution-producing writes.",
        )

    application = Application(
        tenant_id=tenant_id,
        job_id=data.job_id,
        resume_id=data.resume_id,
        apply_mode=data.apply_mode,
        status=(
            ApplicationStatus.QUEUED
            if data.apply_mode == "autonomous"
            else ApplicationStatus.PENDING_REVIEW
        ),
    )
    db.add(application)
    await db.commit()
    await db.refresh(application)

    if data.apply_mode == "autonomous":
        await _enqueue_application_execution(db, application, reason="create_autonomous")

    logger.info("application_created", app_id=application.id, job_id=data.job_id)
    return application


async def create_batch(
    db: AsyncSession,
    data: ApplicationBatchCreate,
) -> list[Application]:
    """Create multiple applications at once.

    Args:
        db: Async database session.
        data: Batch creation data containing multiple job IDs.

    Returns:
        List of newly created Applications.
    """
    applications: list[Application] = []
    for job_id in data.job_ids:
        tenant_id = await _resolve_tenant_for_application(
            db,
            job_id=job_id,
            resume_id=data.resume_id,
            requested_tenant_id=data.tenant_id,
        )
        if data.apply_mode == "autonomous" and not tenant_id:
            raise ValueError(
                "Tenant context is required for autonomous execution-producing writes.",
            )
        app = Application(
            tenant_id=tenant_id,
            job_id=job_id,
            resume_id=data.resume_id,
            apply_mode=data.apply_mode,
            status=(
                ApplicationStatus.QUEUED
                if data.apply_mode == "autonomous"
                else ApplicationStatus.PENDING_REVIEW
            ),
        )
        db.add(app)
        applications.append(app)

    await db.commit()
    for app in applications:
        await db.refresh(app)

    if data.apply_mode == "autonomous":
        for app in applications:
            await _enqueue_application_execution(db, app, reason="batch_create_autonomous")

    logger.info("batch_applications_created", count=len(applications))
    return applications


async def list_applications(
    db: AsyncSession,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    status: str | None = None,
    tenant_id: str | None = None,
) -> ApplicationListResponse:
    """List applications with pagination and optional status filter.

    Args:
        db: Async database session.
        page: Page number (1-indexed).
        page_size: Items per page.
        status: Optional status filter.

    Returns:
        Paginated application list response.
    """
    page_size = min(page_size, MAX_PAGE_SIZE)
    offset = (page - 1) * page_size

    query = select(Application)
    count_query = select(func.count(Application.id))

    if tenant_id is not None:
        query = query.where(Application.tenant_id == tenant_id)
        count_query = count_query.where(Application.tenant_id == tenant_id)

    if status:
        query = query.where(Application.status == status)
        count_query = count_query.where(Application.status == status)

    query = query.order_by(Application.created_at.desc()).offset(offset).limit(page_size)

    result = await db.execute(query)
    apps = list(result.scalars().all())

    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    items = [ApplicationResponse.model_validate(a) for a in apps]

    return ApplicationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=(page * page_size) < total,
    )


async def get_application(
    db: AsyncSession,
    app_id: str,
    tenant_id: str | None = None,
) -> Application:
    """Get a single application by ID.

    Args:
        db: Async database session.
        app_id: UUID of the application.

    Returns:
        The Application model instance.

    Raises:
        RecordNotFoundError: If application does not exist.
    """
    query = select(Application).where(Application.id == app_id)
    if tenant_id is not None:
        query = query.where(Application.tenant_id == tenant_id)

    result = await db.execute(query)
    app = result.scalar_one_or_none()
    if app is None:
        raise RecordNotFoundError("Application", app_id)
    return app


async def approve_application(
    db: AsyncSession,
    app_id: str,
    tenant_id: str | None = None,
) -> Application:
    """Approve a pending application for submission.

    Args:
        db: Async database session.
        app_id: UUID of the application to approve.

    Returns:
        The updated Application.

    Raises:
        RecordNotFoundError: If application does not exist.
    """
    app = await get_application(db, app_id, tenant_id=tenant_id)
    if app.tenant_id is None and tenant_id is not None:
        app.tenant_id = tenant_id
        await db.commit()
        await db.refresh(app)
    if app.tenant_id is None:
        raise ValueError(
            "Tenant context is required for approval that triggers execution.",
        )

    if app.execution_task_id:
        logger.info(
            "application_already_enqueued",
            app_id=app_id,
            task_id=app.execution_task_id,
        )
        return app

    if app.status not in (ApplicationStatus.PENDING_REVIEW, ApplicationStatus.QUEUED):
        raise ValueError(
            f"Cannot approve application in '{app.status}' state. "
            "Only pending_review or queued applications can be approved."
        )
    app.status = ApplicationStatus.APPROVED
    await db.commit()
    await db.refresh(app)
    await _enqueue_application_execution(db, app, reason="approve")
    logger.info("application_approved", app_id=app_id)
    return app


async def update_status(
    db: AsyncSession,
    app_id: str,
    update: ApplicationStatusUpdate,
    tenant_id: str | None = None,
) -> Application:
    """Update an application's status and optional notes.

    Args:
        db: Async database session.
        app_id: UUID of the application.
        update: Status update payload.

    Returns:
        The updated Application.

    Raises:
        RecordNotFoundError: If application does not exist.
    """
    app = await get_application(db, app_id, tenant_id=tenant_id)
    app.status = update.status
    if update.notes is not None:
        app.notes = update.notes
    if update.status == ApplicationStatus.APPLIED:
        app.applied_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(app)
    logger.info("application_status_updated", app_id=app_id, status=update.status)
    return app
