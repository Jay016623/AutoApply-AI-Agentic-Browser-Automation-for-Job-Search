# Queue Reliability & Execution Guarantees

## Queue contract
Envelope fields (v1):
- `attempt_id`
- `tenant_id`
- `idempotency_key`
- `trace_id`
- `created_at`
- `retry_count`

## Leasing / visibility timeout
- Workers now lease messages (`lease_message`) and put them in in-flight storage.
- A lease expiry is tracked per message.
- Expired leases are re-queued automatically (`requeue_expired_leases`) so crashed workers do not lose work.

## Idempotency and duplicate prevention
- Enqueue path enforces idempotency at queue level via Redis `SET NX` dedupe key.
- Duplicate in-flight/enqueued idempotency keys are rejected.

## Retry and dead-letter
- Runtime failures are classified into retry delay buckets (timeout/rate/auth/captcha/default).
- Retries use exponential backoff delay.
- After max retries, jobs are dead-lettered.

## Worker concurrency control
- Global in-flight limit derived from worker/browser parallel setting.
- Per-tenant in-flight cap enforced in runtime.
- Over-limit jobs are safely requeued.

## Heartbeats
- Worker emits periodic lease heartbeats while processing.
- Heartbeats extend lease expiration and emit `job_heartbeat` audit events.

## Audit events
Queue runtime now emits:
- `job_enqueued`
- `job_started`
- `job_heartbeat`
- `job_completed`
- `job_failed`
- `job_dead_lettered`

## Diagnostics
Admin diagnostics include queue reliability counters:
- queue size
- in-flight jobs
- dead-letter count

## Known limitations
- Visibility timeout extension is heartbeat-based and assumes event loop health.
- Delayed retries currently re-enter the main queue directly (no separate delayed ZSET dispatcher in this pass).
- Dedupe TTL is time-based and may need tuning for long-running attempts.
