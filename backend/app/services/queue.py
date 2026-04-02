"""Redis-based task queue service.

Provides simple enqueue/dequeue operations for background job processing.
Workers consume from these queues to apply to jobs, scrape listings, etc.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

from app.db.session import async_session_factory
from app.observability.metrics import queue_dead_letter_total, queue_depth
from app.services.audit import AuditLogCreate, record_audit_log

logger = structlog.get_logger(__name__)


def _queue_inflight_hash(queue_name: str) -> str:
    return f"{queue_name}:inflight"


def _queue_lease_zset(queue_name: str) -> str:
    return f"{queue_name}:leases"


def _queue_dedupe_prefix(queue_name: str) -> str:
    return f"{queue_name}:dedupe:"


async def _audit_queue_event(
    *,
    event_type: str,
    tenant_id: str | None,
    attempt_id: str | None,
    message: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    try:
        async with async_session_factory() as db:
            await record_audit_log(
                db,
                AuditLogCreate(
                    tenant_id=tenant_id,
                    entity_type="application_attempt",
                    entity_id=attempt_id or "queue-unknown",
                    event_type=event_type,
                    message=message,
                    event_metadata=metadata or {},
                ),
            )
    except Exception:  # noqa: BLE001
        logger.debug("queue.audit_event_skipped", event_type=event_type)


def build_envelope(
    *,
    payload: dict[str, Any],
    tenant_id: str | None,
    trace_id: str | None = None,
    attempt_id: str | None = None,
    idempotency_key: str | None = None,
    retry_count: int = 0,
    max_retries: int = 3,
) -> dict[str, Any]:
    """Build normalized queue envelope for worker-safe processing."""
    return {
        "version": 1,
        "tenant_id": tenant_id,
        "trace_id": trace_id or uuid.uuid4().hex,
        "attempt_id": attempt_id,
        "idempotency_key": idempotency_key,
        "retry_count": retry_count,
        "max_retries": max_retries,
        "payload": payload,
        "created_at": datetime.now(UTC).isoformat(),
    }


def normalize_envelope(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy queue message shape into current envelope contract."""
    payload = raw.get("payload", {}) if isinstance(raw.get("payload"), dict) else {}
    if "version" in raw:
        return raw
    # Legacy message (task wrapper) compatibility.
    return build_envelope(
        payload=payload,
        tenant_id=payload.get("tenant_id"),
        trace_id=payload.get("trace_id"),
        attempt_id=payload.get("attempt_id"),
        idempotency_key=payload.get("execution_idempotency_key"),
        retry_count=int(payload.get("retry_count", 0) or 0),
    )


async def enqueue(
    redis: Redis,
    queue_name: str,
    payload: dict,
) -> str:
    """Push a task onto a Redis queue.

    Args:
        redis: Async Redis client.
        queue_name: Name of the Redis list to push to.
        payload: Task data to serialize as JSON.

    Returns:
        Unique task ID assigned to the enqueued task.
    """
    task_id = uuid.uuid4().hex
    message = {
        "task_id": task_id,
        "payload": payload,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    await redis.rpush(queue_name, json.dumps(message))
    queue_depth.labels(queue_name=queue_name).inc()
    logger.info("task_enqueued", task_id=task_id, queue=queue_name)
    return task_id


async def enqueue_envelope(redis: Redis, queue_name: str, envelope: dict[str, Any]) -> str:
    """Enqueue a prebuilt envelope while keeping task wrapper contract."""
    idempotency_key = envelope.get("idempotency_key")
    if isinstance(idempotency_key, str) and idempotency_key:
        dedupe_key = f"{_queue_dedupe_prefix(queue_name)}{idempotency_key}"
        acquired = await redis.set(dedupe_key, "1", nx=True, ex=24 * 3600)
        if not acquired:
            logger.warning("task_enqueue_duplicate_rejected", queue=queue_name, idempotency_key=idempotency_key)
            return ""
    task_id = uuid.uuid4().hex
    message = {
        "task_id": task_id,
        "payload": envelope,
        "enqueued_at": datetime.now(UTC).isoformat(),
    }
    await redis.rpush(queue_name, json.dumps(message))
    queue_depth.labels(queue_name=queue_name).inc()
    logger.info(
        "task_enqueued",
        task_id=task_id,
        queue=queue_name,
        trace_id=envelope.get("trace_id"),
        tenant_id=envelope.get("tenant_id"),
        retry_count=envelope.get("retry_count", 0),
    )
    await _audit_queue_event(
        event_type="job_enqueued",
        tenant_id=envelope.get("tenant_id"),
        attempt_id=envelope.get("attempt_id"),
        message=f"queued:{queue_name}",
        metadata={"queue": queue_name, "task_id": task_id, "trace_id": envelope.get("trace_id")},
    )
    return task_id


async def lease_message(
    redis: Redis,
    queue_name: str,
    *,
    visibility_timeout_seconds: int = 120,
    timeout: int = 5,
) -> dict | None:
    """Claim a queue message with a visibility timeout lease."""
    await requeue_expired_leases(redis, queue_name)
    result = await redis.blpop(queue_name, timeout=timeout)
    if result is None:
        return None
    _queue, raw = result
    message = json.loads(raw)
    message_id = message.get("task_id") or uuid.uuid4().hex
    message["task_id"] = message_id
    deadline = datetime.now(UTC).timestamp() + visibility_timeout_seconds
    await redis.hset(_queue_inflight_hash(queue_name), message_id, json.dumps(message))
    await redis.zadd(_queue_lease_zset(queue_name), {message_id: deadline})
    queue_depth.labels(queue_name=queue_name).dec()
    logger.info("task_leased", queue=queue_name, task_id=message_id, lease_seconds=visibility_timeout_seconds)
    return message


async def heartbeat_lease(redis: Redis, queue_name: str, message_id: str, *, visibility_timeout_seconds: int = 120) -> None:
    deadline = datetime.now(UTC).timestamp() + visibility_timeout_seconds
    await redis.zadd(_queue_lease_zset(queue_name), {message_id: deadline})


async def ack_leased_message(redis: Redis, queue_name: str, message_id: str) -> None:
    await redis.hdel(_queue_inflight_hash(queue_name), message_id)
    await redis.zrem(_queue_lease_zset(queue_name), message_id)


async def requeue_expired_leases(redis: Redis, queue_name: str) -> int:
    now_ts = datetime.now(UTC).timestamp()
    expired_ids = await redis.zrangebyscore(_queue_lease_zset(queue_name), min=0, max=now_ts)
    restored = 0
    for raw_id in expired_ids:
        message_id = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else str(raw_id)
        message_raw = await redis.hget(_queue_inflight_hash(queue_name), message_id)
        if message_raw:
            await redis.rpush(queue_name, message_raw)
            queue_depth.labels(queue_name=queue_name).inc()
            restored += 1
        await redis.hdel(_queue_inflight_hash(queue_name), message_id)
        await redis.zrem(_queue_lease_zset(queue_name), message_id)
    if restored:
        logger.warning("queue_leases_requeued", queue=queue_name, restored=restored)
    return restored


async def get_queue_depth(redis: Redis, queue_name: str) -> int:
    """Get the number of pending tasks in a queue.

    Args:
        redis: Async Redis client.
        queue_name: Name of the Redis list.

    Returns:
        Number of items currently in the queue.
    """
    depth = await redis.llen(queue_name)
    queue_depth.labels(queue_name=queue_name).set(depth)
    return depth


async def dead_letter(
    redis: Redis,
    *,
    dead_letter_queue: str,
    envelope: dict[str, Any],
    reason: str,
    error: str | None = None,
) -> str:
    """Push envelope to dead-letter queue with failure metadata."""
    dead_letter_event = {
        "envelope": envelope,
        "reason": reason,
        "error": error,
        "dead_lettered_at": datetime.now(UTC).isoformat(),
    }
    event_id = uuid.uuid4().hex
    await redis.rpush(dead_letter_queue, json.dumps(dead_letter_event))
    queue_dead_letter_total.labels(queue_name=dead_letter_queue, reason=reason).inc()
    queue_depth.labels(queue_name=dead_letter_queue).inc()
    logger.error(
        "task_dead_lettered",
        event_id=event_id,
        queue=dead_letter_queue,
        reason=reason,
        trace_id=envelope.get("trace_id"),
        tenant_id=envelope.get("tenant_id"),
    )
    await _audit_queue_event(
        event_type="job_dead_lettered",
        tenant_id=envelope.get("tenant_id"),
        attempt_id=envelope.get("attempt_id"),
        message=reason,
        metadata={"queue": dead_letter_queue, "reason": reason, "error": error, "event_id": event_id},
    )
    return event_id


async def queue_diagnostics(redis: Redis, queue_name: str, dead_letter_queue: str) -> dict[str, int]:
    return {
        "queue_size": int(await redis.llen(queue_name)),
        "inflight_jobs": int(await redis.hlen(_queue_inflight_hash(queue_name))),
        "dead_letter_count": int(await redis.llen(dead_letter_queue)),
    }
