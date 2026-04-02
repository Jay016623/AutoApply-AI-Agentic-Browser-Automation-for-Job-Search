"""Audit log service skeleton for operational and compliance events."""

from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class AuditLogCreate:
    """Payload for recording an audit event."""

    entity_type: str
    entity_id: str
    event_type: str
    message: str = ""
    status: str = "recorded"
    tenant_id: str | None = None
    actor_id: str | None = None
    actor_type: str = "system"
    event_metadata: dict[str, Any] | None = None


async def record_audit_log(
    db: AsyncSession,
    payload: AuditLogCreate,
) -> AuditLog:
    """Persist a single audit event.

    This helper is additive and intentionally generic so services/workers
    can adopt it incrementally without behavioral changes.
    """
    row = AuditLog(
        tenant_id=payload.tenant_id,
        actor_id=payload.actor_id,
        actor_type=payload.actor_type,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        event_type=payload.event_type,
        status=payload.status,
        message=payload.message,
        event_metadata=payload.event_metadata,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    logger.info(
        "audit_log.recorded",
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        event_type=payload.event_type,
        status=payload.status,
    )
    return row
