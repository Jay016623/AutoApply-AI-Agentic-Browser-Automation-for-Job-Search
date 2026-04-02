# Intelligent Review Routing & Risk Scoring

## Scoring model
The execution pipeline now computes risk/confidence at three gates:
1. before submission
2. after form fill
3. after verification

Inputs are currently heuristic and pluggable:
- job match confidence (ATS-derived)
- document tailoring confidence
- submission verification confidence
- policy flags (captcha, selector drift, missing fields, etc.)

## Risk classes
- `low_risk`
- `medium_risk`
- `high_risk`

## Review routing reasons
- `low_confidence_match`
- `missing_required_fields`
- `ambiguous_form_state`
- `captcha_detected`
- `selector_drift`
- `unknown_ui_pattern`
- `duplicate_application_risk`

## Decision policy
- low risk => continue autonomously
- medium risk => tenant policy driven (`feature_overrides.medium_risk_requires_review`, default `true`)
- high risk => route to review
- manual override still routes to review

## Auditing
Each gate emits:
- `risk_evaluated`
- `routed_to_review` (when routed)

## Persistence changes
`application_attempts` adds:
- `risk_score`
- `confidence_score`
- `risk_level`

Migration: `20260402_0013_attempt_risk_scoring`.

## Known limitations
- Current scoring is heuristic and not ML-based.
- Tailoring confidence currently inferred from execution context availability.
- Policy is tenant-level via JSON override, not yet a dedicated policy table.
