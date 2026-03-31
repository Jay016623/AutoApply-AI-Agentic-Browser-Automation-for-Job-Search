# Worker Queue Envelope Contract (Phase 1 Hardening)

## Envelope
```json
{
  "version": 1,
  "tenant_id": "tenant_...",
  "trace_id": "uuid-like",
  "attempt_id": "attempt_id_or_null",
  "idempotency_key": "stable_key_or_null",
  "retry_count": 0,
  "max_retries": 3,
  "payload": {
    "application_id": "...",
    "job_id": "...",
    "platform": "linkedin"
  },
  "created_at": "ISO-8601"
}
```

## Required payload fields
- `application_id`
- `job_id`
- `platform`

Invalid envelopes are dead-lettered to `autoapply:queue:apply:dead_letter`.

## Dead-letter event
```json
{
  "envelope": { "...": "..." },
  "reason": "invalid_envelope | retries_exhausted",
  "error": "string_or_null",
  "dead_lettered_at": "ISO-8601"
}
```

## Retry semantics
- Unexpected worker runtime exceptions are treated as transient.
- Message is re-enqueued with incremented `retry_count`.
- On `retry_count > max_retries`, message moves to dead-letter queue.

## Compatibility
Legacy queue shape (`{"task_id": ..., "payload": {...}}`) is normalized into envelope form by worker runtime.
