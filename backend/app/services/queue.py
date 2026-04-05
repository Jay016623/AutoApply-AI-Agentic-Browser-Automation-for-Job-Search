"""Redis-based task queue service.

Provides simple enqueue/dequeue operations for background job processing.
Workers consume from these queues to apply to jobs, scrape listings, etc.
"""

import json
import uuid
from datetime import UTC, datetime

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)


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
    logger.info("task_enqueued", task_id=task_id, queue=queue_name)
    return task_id


async def enqueue_idempotent(
    redis: Redis,
    queue_name: str,
    payload: dict,
    *,
    idempotency_key: str,
    lock_ttl_seconds: int = 24 * 60 * 60,
) -> tuple[str, bool]:
    """Enqueue a task once for a deterministic idempotency key.

    The idempotency lock key uses Redis SET NX with TTL:
      queue:idempotency:{queue_name}:{idempotency_key}
    - First caller sets a generated task_id and enqueues payload.
    - Repeat callers receive the same task_id and do not enqueue again.

    Returns:
        (task_id, enqueued_now)
    """
    lock_key = f"queue:idempotency:{queue_name}:{idempotency_key}"
    task_id = uuid.uuid4().hex
    created = await redis.set(lock_key, task_id, ex=lock_ttl_seconds, nx=True)

    if created:
        message = {
            "task_id": task_id,
            "payload": payload,
            "enqueued_at": datetime.now(UTC).isoformat(),
        }
        await redis.rpush(queue_name, json.dumps(message))
        logger.info(
            "task_enqueued_idempotent",
            task_id=task_id,
            queue=queue_name,
            idempotency_key=idempotency_key,
            ttl=lock_ttl_seconds,
        )
        return task_id, True

    existing_task_id = await redis.get(lock_key)
    if isinstance(existing_task_id, bytes):
        existing_task_id = existing_task_id.decode()
    resolved_task_id = existing_task_id or task_id
    logger.info(
        "task_enqueue_idempotent_suppressed",
        task_id=resolved_task_id,
        queue=queue_name,
        idempotency_key=idempotency_key,
    )
    return str(resolved_task_id), False


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
    return await redis.llen(queue_name)
