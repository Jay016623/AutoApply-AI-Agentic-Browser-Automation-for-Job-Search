"""Unit tests for queue envelope, retry, and dead-letter semantics."""

import json

import pytest
from fakeredis.aioredis import FakeRedis

from app.services import queue

QUEUE_NAME = "test:queue"
PROCESSING_QUEUE = "test:queue:processing"
DLQ = "test:queue:dlq"


@pytest.fixture
def fake_redis():
    client = FakeRedis()
    yield client


class TestEnvelope:
    def test_parse_legacy_message(self):
        legacy = {
            "task_id": "legacy-task",
            "payload": {"application_id": "app-1", "tenant_id": "t-1"},
            "enqueued_at": "2026-01-01T00:00:00+00:00",
        }

        envelope = queue.parse_message(legacy)

        assert envelope.task_id == "legacy-task"
        assert envelope.payload["application_id"] == "app-1"
        assert envelope.retry_count == 0
        assert envelope.tenant_id == "t-1"

    async def test_enqueue_writes_v2_envelope(self, fake_redis):
        await queue.enqueue(fake_redis, QUEUE_NAME, {"job_id": "job-1"})

        raw = await fake_redis.lpop(QUEUE_NAME)
        msg = json.loads(raw)

        assert msg["version"] == queue.ENVELOPE_VERSION
        assert "attempt_id" in msg
        assert msg["retry_count"] == 0


class TestRetryAndDeadLetter:
    async def test_retry_increments_count_and_requeues(self, fake_redis):
        await queue.enqueue(fake_redis, QUEUE_NAME, {"job_id": "job-1"}, max_retries=2)
        message = await queue.reserve(
            fake_redis,
            QUEUE_NAME,
            PROCESSING_QUEUE,
            timeout=1,
            visibility_timeout_seconds=30,
        )

        disposition = await queue.retry_or_dead_letter(
            fake_redis,
            queue_name=QUEUE_NAME,
            processing_queue_name=PROCESSING_QUEUE,
            dead_letter_queue_name=DLQ,
            message=message,
        )

        assert disposition == "requeued"
        requeued = json.loads(await fake_redis.rpop(QUEUE_NAME))
        assert requeued["retry_count"] == 1
        assert await fake_redis.llen(DLQ) == 0

    async def test_exhausted_retry_moves_to_dead_letter(self, fake_redis):
        msg = queue.build_envelope(
            {"job_id": "job-1"},
            retry_count=2,
            max_retries=2,
        ).to_dict()
        await fake_redis.rpush(PROCESSING_QUEUE, json.dumps(msg))

        disposition = await queue.retry_or_dead_letter(
            fake_redis,
            queue_name=QUEUE_NAME,
            processing_queue_name=PROCESSING_QUEUE,
            dead_letter_queue_name=DLQ,
            message=msg,
        )

        assert disposition == "dead_lettered"
        assert await fake_redis.llen(QUEUE_NAME) == 0
        dead = json.loads(await fake_redis.rpop(DLQ))
        assert dead["task_id"] == msg["task_id"]
        assert "dead_lettered_at" in dead
