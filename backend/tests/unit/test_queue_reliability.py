"""Tests for queue reliability helpers."""

from app.services.queue import build_envelope
from app.workers.orchestration.queue_runtime import _retry_delay_seconds


def test_build_envelope_contract_fields() -> None:
    envelope = build_envelope(
        payload={"application_id": "a1", "job_id": "j1", "platform": "linkedin"},
        tenant_id="tenant-1",
        attempt_id="attempt-1",
        idempotency_key="idem-1",
        retry_count=2,
    )
    assert envelope["attempt_id"] == "attempt-1"
    assert envelope["tenant_id"] == "tenant-1"
    assert envelope["idempotency_key"] == "idem-1"
    assert envelope["trace_id"]
    assert envelope["created_at"]
    assert envelope["retry_count"] == 2


def test_retry_delay_mapping() -> None:
    assert _retry_delay_seconds("timeout while loading", 1) == 30
    assert _retry_delay_seconds("captcha challenge", 1) == 120
    assert _retry_delay_seconds("unknown failure", 1) == 10
