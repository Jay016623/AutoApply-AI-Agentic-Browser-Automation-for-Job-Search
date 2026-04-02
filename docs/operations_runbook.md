# Production Operations Runbook (Modular Monolith)

## Purpose
This runbook covers readiness checks, diagnostics, and first-response procedures for multi-tenant production incidents.

## Health and readiness endpoints
- **Liveness:** `GET /healthz`
- **Basic health:** `GET /health`
- **Readiness:** `GET /readyz`
- **Admin readiness (RBAC):** `GET /api/v1/admin/ready`
- **Admin diagnostics (RBAC):** `GET /api/v1/admin/diagnostics`

## What readiness validates
- API process is serving
- Database connectivity (`SELECT 1`)
- Redis connectivity (`PING`)
- Artifact backend health (local write probe or S3 `HeadBucket`)
- Queue depth snapshot for apply/scrape/generate/dead-letter

`/readyz` and `/api/v1/admin/ready` return degraded/503 if critical dependencies are down.

## Key metrics to monitor
- `autoapply_workflow_transitions_total` (workflow throughput)
- `autoapply_retry_events_total` (retry lifecycle)
- `autoapply_queue_dead_letter_total` (dead-letter pressure)
- `autoapply_review_queue_open` and `autoapply_review_queue_total`
- `autoapply_automation_runs_total` (success/failure by platform)
- `autoapply_artifact_storage_bytes_total` (artifact growth)
- Existing queue depth and queue processing latency metrics

## First response checklist
1. Check `GET /readyz`.
2. Check queue pressure via `GET /api/v1/admin/diagnostics`.
3. Confirm dead-letter growth (`autoapply_queue_dead_letter_total`).
4. Confirm retry escalations (`autoapply_retry_events_total{status="manual_escalated"}`).
5. Check platform-specific failures (`autoapply_automation_runs_total{outcome="failure"}`).
6. If failures spike, inspect structured logs keyed by:
   - `trace_id`
   - `tenant_id`
   - `workflow_run_id` / `attempt_id`

## Configuration hardening in staging/production
Startup now fails fast when:
- `AUTH__TOKEN_SECRET` is empty/default
- `DATABASE_URL` is empty
- `REDIS_URL` is empty
- S3 artifact storage is selected without bucket/access key/secret key

## Safe maintenance guidance
- Keep strict tenant startup validation enabled by default.
- During incident mitigation, prefer reducing worker concurrency / pausing scheduler over disabling tenant enforcement.
- Use admin diagnostics to estimate backlog recovery before re-enabling full throughput.

## Remaining operational risks
- Redis outages still block queue-driven automation execution paths.
- S3 transient permission/network failures can degrade artifact persistence.
- Queue depth gauges are eventually consistent under process restarts.
- Some diagnostics aggregate globally (not per tenant), so tenant hot-spotting still needs log-level investigation.
