# Strict Tenant Enforcement Rollout (Phase 1 Hardening)

## What changed
- Runtime strict mode now defaults on in non-development environments via `Settings.strict_tenant_enforcement`.
- Startup validation can run safe tenant backfills and fail fast if critical entities still have `tenant_id IS NULL`.
- DB hardening migration (`20260402_0011`) backfills and tightens NOT NULL on:
  - `applications.tenant_id`
  - `workflow_runs.tenant_id`
  - `application_attempts.tenant_id`
  - `proof_artifacts.tenant_id`
  - `review_tasks.tenant_id`

## Feature flags
- `FEATURE__TENANT_ENFORCEMENT` (legacy/explicit toggle)
- `FEATURE__STRICT_TENANT_STARTUP_VALIDATION` (startup guardrail)

## Safe rollout sequence
1. Deploy code with startup validation enabled in staging.
2. Run migrations through `20260402_0011`.
3. Observe startup logs for `tenant_backfill_report`.
4. If startup fails, inspect null ownership counts and fix source ownership first.
5. Enable in pilot prod once counts are clean.

## Rollback strategy
- Immediate runtime fallback: set `FEATURE__STRICT_TENANT_STARTUP_VALIDATION=false` to bypass startup hard-fail while investigating ownership gaps.
- Migration rollback: downgrade `20260402_0011` to restore nullable tenant fields on hardened tables.
- Keep `FEATURE__TENANT_ENFORCEMENT=true` in pilot unless emergency break-glass is required.

## Entities intentionally left looser (for now)
- `jobs.tenant_id`
- `candidates.tenant_id`

Rationale: some historical records may not have deterministic ownership lineage. These remain startup-validated and backfilled where safe, but are not forcibly NOT NULL in this phase to avoid unsafe data assumptions.
