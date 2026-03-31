"""Queue runtime orchestration for apply worker reliability semantics."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from redis.asyncio import Redis

from app.config.constants import QUEUE_APPLY, QUEUE_APPLY_DEAD_LETTER
from app.services.queue import dead_letter, enqueue_envelope, normalize_envelope

logger = structlog.get_logger(__name__)


class EnvelopeValidationError(Exception):
    """Message cannot be processed due to malformed payload/envelope."""


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
) -> None:
    """Process one apply queue message with retry/dead-letter semantics."""
    envelope = normalize_envelope(message.get("payload", {}))
    trace_id = envelope.get("trace_id")
    retry_count = int(envelope.get("retry_count", 0) or 0)
    max_retries = int(envelope.get("max_retries", 3) or 3)

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
        return

    payload = envelope["payload"]
    payload.setdefault("trace_id", trace_id)
    payload.setdefault("tenant_id", envelope.get("tenant_id"))

    try:
        await handler(payload)
        logger.info(
            "worker.message_processed",
            trace_id=trace_id,
            tenant_id=envelope.get("tenant_id"),
            retry_count=retry_count,
        )
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
            return

        retry_envelope = {
            **envelope,
            "retry_count": retry_count + 1,
            "last_error": str(exc),
        }
        await enqueue_envelope(redis, QUEUE_APPLY, retry_envelope)
        logger.warning(
            "worker.message_requeued",
            trace_id=trace_id,
            retry_count=retry_count + 1,
            max_retries=max_retries,
            error=str(exc),
        )
