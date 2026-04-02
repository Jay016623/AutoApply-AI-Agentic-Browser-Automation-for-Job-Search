# Artifact Evidence Hardening Notes

## What changed
- Artifact object keys now follow:
  - `tenant_id/{...}/application_id/{...}/attempt_id/{...}/step_id/{...}/artifact_type/{...}/timestamp...`
- Durable artifact writes now include explicit execution request/response payload captures.
- Step failures always emit an `execution_failure` structured artifact.
- Execution API now supports listing artifacts by step in addition to by attempt.

## Backward compatibility
- Existing records with placeholder-style paths (`attempt://`, `adapter://`) are still retrievable via download URL endpoint.
- If a legacy artifact has `metadata_json.captured_path` pointing to an existing local file, that path is returned.
- Otherwise the original legacy storage path is returned as-is.

## Retrieval APIs
- `GET /api/v1/execution/attempts/{attempt_id}/artifacts`
- `GET /api/v1/execution/steps/{attempt_step_id}/artifacts`
- `GET /api/v1/execution/artifacts/{artifact_id}/download-url`

## Migration note
- No schema migration required for this hardening pass because `proof_artifacts` already stores backend/key/content-type/size/checksum/step linkage.

## Known limitations
- Legacy placeholder artifacts cannot be backfilled into object storage automatically without source bytes.
- Local backend download URLs are local paths (suitable for trusted internal deployments/dev).
