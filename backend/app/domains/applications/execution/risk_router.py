"""Risk and confidence scoring for autonomous execution routing."""

from __future__ import annotations

from dataclasses import dataclass


REVIEW_REASONS = {
    "low_confidence_match",
    "missing_required_fields",
    "ambiguous_form_state",
    "captcha_detected",
    "selector_drift",
    "unknown_ui_pattern",
    "duplicate_application_risk",
}


@dataclass(frozen=True)
class RiskSignals:
    job_match_confidence: float
    document_tailoring_confidence: float
    submission_verification_confidence: float
    flags: set[str]


@dataclass(frozen=True)
class RiskDecision:
    risk_score: float
    confidence_score: float
    risk_level: str
    route_to_review: bool
    reason: str | None


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def score_risk(signals: RiskSignals) -> RiskDecision:
    avg_conf = _clamp((signals.job_match_confidence + signals.document_tailoring_confidence + signals.submission_verification_confidence) / 3.0)
    risk_score = _clamp(1.0 - avg_conf)

    if "captcha_detected" in signals.flags or "unknown_ui_pattern" in signals.flags:
        risk_score = max(risk_score, 0.9)
    if "selector_drift" in signals.flags or "ambiguous_form_state" in signals.flags:
        risk_score = max(risk_score, 0.7)
    if "duplicate_application_risk" in signals.flags:
        risk_score = max(risk_score, 0.8)

    if risk_score >= 0.75:
        risk_level = "high_risk"
    elif risk_score >= 0.4:
        risk_level = "medium_risk"
    else:
        risk_level = "low_risk"

    reason = next((flag for flag in signals.flags if flag in REVIEW_REASONS), None)
    return RiskDecision(
        risk_score=risk_score,
        confidence_score=avg_conf,
        risk_level=risk_level,
        route_to_review=False,
        reason=reason,
    )


def apply_policy(*, scored: RiskDecision, medium_risk_requires_review: bool, manual_override: bool) -> RiskDecision:
    if manual_override:
        return RiskDecision(
            risk_score=scored.risk_score,
            confidence_score=scored.confidence_score,
            risk_level=scored.risk_level,
            route_to_review=True,
            reason=scored.reason or "ambiguous_form_state",
        )

    if scored.risk_level == "high_risk":
        return RiskDecision(
            risk_score=scored.risk_score,
            confidence_score=scored.confidence_score,
            risk_level=scored.risk_level,
            route_to_review=True,
            reason=scored.reason or "unknown_ui_pattern",
        )

    if scored.risk_level == "medium_risk" and medium_risk_requires_review:
        return RiskDecision(
            risk_score=scored.risk_score,
            confidence_score=scored.confidence_score,
            risk_level=scored.risk_level,
            route_to_review=True,
            reason=scored.reason or "ambiguous_form_state",
        )

    return RiskDecision(
        risk_score=scored.risk_score,
        confidence_score=scored.confidence_score,
        risk_level=scored.risk_level,
        route_to_review=False,
        reason=scored.reason,
    )
