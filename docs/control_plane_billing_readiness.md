# SaaS Control-Plane Basics (Billing Readiness)

## Scope in this batch
This change adds internal plan/quota/feature controls for tenant enforcement without integrating an external billing processor.

## Control model design
- Tenant plan source of truth lives on `tenants`:
  - `plan_key` (`free`, `pro`, `enterprise`)
  - `plan_overrides` (quota overrides)
  - `feature_overrides` (feature switches)
- Plan catalog is static in code (`services/control_plane.py`) and merged with tenant overrides at runtime.

## Quotas implemented
- `candidate_count`
- `daily_applications`
- `artifact_storage_bytes`
- `automation_concurrency`
- `llm_daily_tokens`
- `llm_daily_cost_usd`

## Enforcement points
- Candidate creation (`CandidateService.create_candidate`) -> `candidate_count`
- Application creation/batch (`services/application.py`) -> `daily_applications`
- Artifact writes (`services/artifacts/storage.py`) -> `artifact_storage_bytes`
- Worker apply path (`workers/application_worker.py`) -> `automation_concurrency`
- LLM completions (`core/llm/client.py`, tenant-aware instances) -> token/cost thresholds

## Feature flags (plan-aware)
- `advanced_execution_diagnostics`
- `priority_automation`
- `custom_llm_models`
- `bulk_operations`

`/api/v1/admin/diagnostics` now requires `advanced_execution_diagnostics` when a tenant context is present.

## APIs
- `GET /api/v1/admin/control/plan` - current tenant plan, features, quota usage/remaining
- `PUT /api/v1/admin/control/tenants/{tenant_id}/plan` - owner/admin plan + override update

## Auditing
Quota and feature denials are recorded as audit events:
- `quota.exceeded`
- `feature.denied`
- plan updates are audited as `plan.updated`

## Known gaps before real billing integration
- No Stripe/Chargebee/Recurly integration yet.
- No invoice/proration lifecycle.
- Plan catalog is code-backed (not admin-managed in DB yet).
- Quota accounting uses current-state + same-day aggregates (sufficient for control-plane enforcement, not revenue-grade metering).
