"""Redis-based task queue service.

Provides queue operations with a reliability envelope:
- enqueue into primary queue
- reserve into a processing queue (visibility timeout style)
- ack/nack semantics
- retry bookkeeping and dead-letter support
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

ENVELOPE_VERSION = 2


@dataclass(slots=True)
class QueueEnvelope:
    """Canonical queue envelope used by workers."""

    task_id: str
    payload: dict[str, Any]
    enqueued_at: str
    attempt_id: str
    retry_count: int
    max_retries: int
    trace_id: str | None
    tenant_id: str | None
    lease_expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": ENVELOPE_VERSION,
            "task_id": self.task_id,
            "payload": self.payload,
            "enqueued_at": self.enqueued_at,
            "attempt_id": self.attempt_id,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "trace_id": self.trace_id,
            "tenant_id": self.tenant_id,
            "lease_expires_at": self.lease_expires_at,
        }



def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def build_envelope(
    payload: dict[str, Any],
    *,
    task_id: str | None = None,
    attempt_id: str | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
    trace_id: str | None = None,
    tenant_id: str | None = None,
    enqueued_at: str | None = None,
    lease_expires_at: str | None = None,
) -> QueueEnvelope:
    """Create a queue envelope with sane defaults."""
    payload_tenant = payload.get("tenant_id")
    payload_trace = payload.get("trace_id")

    return QueueEnvelope(
        task_id=task_id or uuid.uuid4().hex,
        payload=payload,
        enqueued_at=enqueued_at or _utc_now_iso(),
        attempt_id=attempt_id or uuid.uuid4().hex,
        retry_count=retry_count,
        max_retries=max_retries,
        trace_id=trace_id if trace_id is not None else payload_trace,
        tenant_id=tenant_id if tenant_id is not None else payload_tenant,
        lease_expires_at=lease_expires_at,
    )


def parse_message(message: dict[str, Any]) -> QueueEnvelope:
    """Normalize legacy and v2 queue messages into a QueueEnvelope."""
    if message.get("version") == ENVELOPE_VERSION:
        return build_envelope(
            task_id=message.get("task_id"),
            payload=message.get("payload", {}),
            enqueued_at=message.get("enqueued_at"),
            attempt_id=message.get("attempt_id"),
            retry_count=int(message.get("retry_count", 0)),
            max_retries=int(message.get("max_retries", 3)),
            trace_id=message.get("trace_id"),
            tenant_id=message.get("tenant_id"),
            lease_expires_at=message.get("lease_expires_at"),
        )

    # Backward compatibility with old shape: {task_id, payload, enqueued_at}
    return build_envelope(
        task_id=message.get("task_id"),
        payload=message.get("payload", {}),
        enqueued_at=message.get("enqueued_at"),
        retry_count=0,
        max_retries=int(message.get("max_retries", 3)),
        trace_id=message.get("trace_id"),
        tenant_id=message.get("tenant_id"),
    )


async def enqueue(
    redis: Redis,
    queue_name: str,
    payload: dict[str, Any],
    *,
    max_retries: int = 3,
    trace_id: str | None = None,
    tenant_id: str | None = None,
) -> str:
    """Push a task envelope onto a Redis queue."""
    envelope = build_envelope(
        payload,
        max_retries=max_retries,
        trace_id=trace_id,
        tenant_id=tenant_id,
    )
    await redis.rpush(queue_name, json.dumps(envelope.to_dict()))
    logger.info(
        "task_enqueued",
        task_id=envelope.task_id,
        attempt_id=envelope.attempt_id,
        queue=queue_name,
        retry_count=envelope.retry_count,
    )
    return envelope.task_id


async def dequeue(
    redis: Redis,
    queue_name: str,
    timeout: int = 5,
) -> dict[str, Any] | None:
    """Pop a task from a Redis queue (legacy helper)."""
    result = await redis.blpop(queue_name, timeout=timeout)
    if result is None:
        return None

    _queue, raw = result
    message = json.loads(raw)
    envelope = parse_message(message)
    logger.debug("task_dequeued", task_id=envelope.task_id, queue=queue_name)
    return envelope.to_dict()


async def reserve(
    redis: Redis,
    queue_name: str,
    processing_queue_name: str,
    *,
    timeout: int = 5,
    visibility_timeout_seconds: int = 120,
) -> dict[str, Any] | None:
    """Atomically move a message to processing queue and attach lease metadata."""
    raw = await redis.brpoplpush(queue_name, processing_queue_name, timeout=timeout)
    if raw is None:
        return None

    message = parse_message(json.loads(raw))
    lease_expiry = datetime.now(UTC).timestamp() + visibility_timeout_seconds
    message.lease_expires_at = datetime.fromtimestamp(lease_expiry, tz=UTC).isoformat()

    # Rewrite leased message in processing queue while preserving list position.
    await redis.lrem(processing_queue_name, 1, raw)
    leased_raw = json.dumps(message.to_dict())
    await redis.lpush(processing_queue_name, leased_raw)

    logger.debug(
        "task_reserved",
        task_id=message.task_id,
        attempt_id=message.attempt_id,
        queue=queue_name,
        processing_queue=processing_queue_name,
        lease_expires_at=message.lease_expires_at,
    )
    return message.to_dict()


async def ack(redis: Redis, processing_queue_name: str, message: dict[str, Any]) -> None:
    """Acknowledge a processed message by removing it from processing queue."""
    removed = await redis.lrem(processing_queue_name, 1, json.dumps(message))
    logger.debug(
        "task_acked",
        task_id=message.get("task_id"),
        attempt_id=message.get("attempt_id"),
        processing_queue=processing_queue_name,
        removed=removed,
    )


async def retry_or_dead_letter(
    redis: Redis,
    *,
    queue_name: str,
    processing_queue_name: str,
    dead_letter_queue_name: str,
    message: dict[str, Any],
) -> str:
    """Retry message or move to dead-letter queue. Returns disposition."""
    envelope = parse_message(message)
    await ack(redis, processing_queue_name, message)

    if envelope.retry_count + 1 > envelope.max_retries:
        dead_message = envelope.to_dict()
        dead_message["dead_lettered_at"] = _utc_now_iso()
        await redis.rpush(dead_letter_queue_name, json.dumps(dead_message))
        logger.warning(
            "task_dead_lettered",
            task_id=envelope.task_id,
            attempt_id=envelope.attempt_id,
            retry_count=envelope.retry_count,
            dead_letter_queue=dead_letter_queue_name,
        )
        return "dead_lettered"

    retry_message = build_envelope(
        payload=envelope.payload,
        task_id=envelope.task_id,
        retry_count=envelope.retry_count + 1,
        max_retries=envelope.max_retries,
        trace_id=envelope.trace_id,
        tenant_id=envelope.tenant_id,
        enqueued_at=envelope.enqueued_at,
    ).to_dict()
    await redis.rpush(queue_name, json.dumps(retry_message))
    logger.info(
        "task_requeued",
        task_id=envelope.task_id,
        queue=queue_name,
        retry_count=retry_message["retry_count"],
    )
    return "requeued"


async def get_queue_depth(redis: Redis, queue_name: str) -> int:
    """Get the number of pending tasks in a queue."""
    return await redis.llen(queue_name)
