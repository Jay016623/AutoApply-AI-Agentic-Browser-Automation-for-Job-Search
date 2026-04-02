"""Queue runtime orchestration for apply worker reliability semantics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import asyncio
import structlog
from redis.asyncio import Redis

from app.config.constants import QUEUE_APPLY, QUEUE_APPLY_DEAD_LETTER
from app.config.settings import get_settings
from app.db.session import async_session_factory
from app.observability.metrics import retry_events_total
from app.services.audit import AuditLogCreate, record_audit_log
from app.services.queue import ack_leased_message, dead_letter, enqueue_envelope, heartbeat_lease, normalize_envelope

logger = structlog.get_logger(__name__)
settings = get_settings()


class EnvelopeValidationError(Exception):
    """Message cannot be processed due to malformed payload/envelope."""


def _retry_delay_seconds(error_text: str, retry_count: int) -> int:
    lowered = error_text.lower()
    if "rate" in lowered or "timeout" in lowered:
        base = 15
    elif "captcha" in lowered or "auth" in lowered:
        base = 60
    else:
        base = 5
    return base * (2 ** max(retry_count, 0))


def _validate_envelope(envelope: dict[str, Any]) -> None:
    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise EnvelopeValidationError("payload_must_be_object")
    required = ["application_id", "job_id", "platform"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        raise EnvelopeValidationError(f"missing_required_payload_fields:{','.join(missing)}")


async def process_apply_message(
    *,
    redis: Redis,
    message: dict[str, Any],
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    queue_name: str = QUEUE_APPLY,
    visibility_timeout_seconds: int = 120,
) -> None:
    """Process one apply queue message with retry/dead-letter semantics."""
    envelope = normalize_envelope(message.get("payload", {}))
    trace_id = envelope.get("trace_id")
    message_id = message.get("task_id")
    retry_count = int(envelope.get("retry_count", 0) or 0)
    max_retries = int(envelope.get("max_retries", 3) or 3)
    logger.info(
        "worker.message_received",
        trace_id=trace_id,
        tenant_id=envelope.get("tenant_id"),
        retry_count=retry_count,
        max_retries=max_retries,
    )

    try:
        _validate_envelope(envelope)
    except EnvelopeValidationError as exc:
        await dead_letter(
            redis,
            dead_letter_queue=QUEUE_APPLY_DEAD_LETTER,
            envelope=envelope,
            reason="invalid_envelope",
            error=str(exc),
        )
        retry_events_total.labels(event_type="runtime_validation", status="dead_lettered").inc()
        if message_id:
            await ack_leased_message(redis, queue_name, str(message_id))
        return

    payload = envelope["payload"]
    payload.setdefault("trace_id", trace_id)
    payload.setdefault("tenant_id", envelope.get("tenant_id"))

    async def _audit(event_type: str, status: str, details: dict[str, Any] | None = None) -> None:
        try:
            async with async_session_factory() as db:
                await record_audit_log(
                    db,
                    AuditLogCreate(
                        tenant_id=envelope.get("tenant_id"),
                        entity_type="application_attempt",
                        entity_id=envelope.get("attempt_id") or str(message_id or "unknown"),
                        event_type=event_type,
                        status=status,
                        message=event_type,
                        event_metadata=details or {},
                    ),
                )
        except Exception:  # noqa: BLE001
            logger.debug("queue_runtime.audit_skipped", event_type=event_type)

    await _audit("job_started", "running", {"trace_id": trace_id, "retry_count": retry_count})
    tenant_id = envelope.get("tenant_id")
    global_limit = max(1, int(getattr(settings.browser, "max_parallel", 3)))
    tenant_limit = 2
    global_key = "autoapply:workers:inflight:global"
    tenant_key = f"autoapply:workers:inflight:tenant:{tenant_id}" if tenant_id else None
    global_inflight = await redis.incr(global_key)
    tenant_inflight = await redis.incr(tenant_key) if tenant_key else 0
    if global_inflight > global_limit or (tenant_key and tenant_inflight > tenant_limit):
        await redis.decr(global_key)
        if tenant_key:
            await redis.decr(tenant_key)
        retry_envelope = {**envelope, "retry_count": retry_count, "last_error": "concurrency_limit"}
        await enqueue_envelope(redis, QUEUE_APPLY, retry_envelope)
        if message_id:
            await ack_leased_message(redis, queue_name, str(message_id))
        await _audit(
            "job_failed",
            "retry_scheduled",
            {"reason": "concurrency_limit", "global_inflight": global_inflight, "tenant_inflight": tenant_inflight},
        )
        return

    stop_heartbeat = asyncio.Event()

    async def _heartbeat_loop() -> None:
        while not stop_heartbeat.is_set():
            if message_id:
                await heartbeat_lease(
                    redis,
                    queue_name,
                    str(message_id),
                    visibility_timeout_seconds=visibility_timeout_seconds,
                )
                await _audit("job_heartbeat", "running", {"trace_id": trace_id})
            await asyncio.sleep(max(5, visibility_timeout_seconds // 3))

    heartbeat_task = asyncio.create_task(_heartbeat_loop())

    try:
        await handler(payload)
        logger.info(
            "worker.message_processed",
            trace_id=trace_id,
            tenant_id=envelope.get("tenant_id"),
            retry_count=retry_count,
        )
        await _audit("job_completed", "completed", {"trace_id": trace_id})
        if message_id:
            await ack_leased_message(redis, queue_name, str(message_id))
    except Exception as exc:  # noqa: BLE001
        # Treat unexpected runtime failures as transient until retries exhausted.
        if retry_count + 1 > max_retries:
            await dead_letter(
                redis,
                dead_letter_queue=QUEUE_APPLY_DEAD_LETTER,
                envelope=envelope,
                reason="retries_exhausted",
                error=str(exc),
            )
            retry_events_total.labels(event_type="runtime_retry", status="dead_lettered").inc()
            await _audit("job_failed", "dead_lettered", {"error": str(exc), "trace_id": trace_id})
            if message_id:
                await ack_leased_message(redis, queue_name, str(message_id))
            return

        delay_seconds = _retry_delay_seconds(str(exc), retry_count)
        retry_envelope = {
            **envelope,
            "retry_count": retry_count + 1,
            "last_error": str(exc),
            "next_retry_delay_seconds": delay_seconds,
        }
        await enqueue_envelope(redis, QUEUE_APPLY, retry_envelope)
        retry_events_total.labels(event_type="runtime_retry", status="requeued").inc()
        await _audit(
            "job_failed",
            "retry_scheduled",
            {"error": str(exc), "trace_id": trace_id, "delay_seconds": delay_seconds, "retry_count": retry_count + 1},
        )
        if message_id:
            await ack_leased_message(redis, queue_name, str(message_id))
        logger.warning(
            "worker.message_requeued",
            trace_id=trace_id,
            retry_count=retry_count + 1,
            max_retries=max_retries,
            error=str(exc),
        )
    finally:
        stop_heartbeat.set()
        heartbeat_task.cancel()
        await redis.decr(global_key)
        if tenant_key:
            await redis.decr(tenant_key)
