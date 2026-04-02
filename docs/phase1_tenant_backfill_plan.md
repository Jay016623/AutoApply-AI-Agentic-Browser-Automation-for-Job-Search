# Phase 1 Tenant Ownership Backfill Plan

## Objective
Backfill missing `tenant_id` on critical entities before enforcing DB-level non-null constraints.

## Critical Entities
- `jobs`
- `applications`
- `resumes`
- `application_attempts`
- `application_attempt_steps`
- `proof_artifacts`
- `candidates`
- `resume_versions`
- `cover_letter_versions`
- `workflow_runs`
- `workflow_steps`

## Strategy (incremental, reversible)
1. **Inventory pass**
   - Run SQL reports for each table: total rows, rows with `tenant_id IS NULL`, grouped by inferred owner fields.
2. **Inference rules**
   - `applications.tenant_id <- jobs.tenant_id`
   - `application_attempts.tenant_id <- applications.tenant_id`
   - `application_attempt_steps.tenant_id <- application_attempts.tenant_id`
   - `proof_artifacts.tenant_id <- application_attempts.tenant_id` (fallback: `applications.tenant_id`)
   - `resumes.tenant_id <- candidates.tenant_id` where candidate linked
   - `resume_versions/cover_letter_versions.tenant_id <- candidates.tenant_id`
   - `workflow_runs/workflow_steps.tenant_id <- applications.tenant_id` where linked
3. **Manual queue for ambiguous rows**
   - Rows still null after inference are exported to a review table/file and blocked from write updates until resolved.
4. **Soft enforcement phase**
   - Keep runtime guards (`tenant_id_required_for_*`) enabled.
   - Monitor for new null rows.
5. **Hard enforcement phase**
   - Add NOT NULL + FK constraints per table in staggered migrations.
   - Remove legacy unscoped write fallback.

## Rollback Plan
- Each migration step should be reversible by:
  - dropping new NOT NULL constraint,
  - restoring nullable behavior,
  - keeping inferred tenant values unchanged.

## Operational Notes
- Run in off-peak windows.
- Snapshot DB before each hard-enforcement migration.
- Validate via tenant-scoped read API smoke tests after each step.
