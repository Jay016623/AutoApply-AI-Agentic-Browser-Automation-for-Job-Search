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

from app.observability.metrics import queue_dead_letter_total, queue_depth

logger = structlog.get_logger(__name__)


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
    return task_id


async def dequeue(
    redis: Redis,
    queue_name: str,
    timeout: int = 5,
) -> dict | None:
    """Pop a task from a Redis queue (blocking).

    Args:
        redis: Async Redis client.
        queue_name: Name of the Redis list to pop from.
        timeout: Blocking timeout in seconds.

    Returns:
        Deserialized task dict, or None if timeout expired.
    """
    result = await redis.blpop(queue_name, timeout=timeout)
    if result is None:
        return None

    _queue, raw = result
    message = json.loads(raw)
    queue_depth.labels(queue_name=queue_name).dec()
    logger.debug("task_dequeued", task_id=message.get("task_id"), queue=queue_name)
    return message


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
    return event_id
