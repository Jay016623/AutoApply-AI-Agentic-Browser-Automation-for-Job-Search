"""Tests for risk scoring and routing policy."""

from app.domains.applications.execution.risk_router import RiskSignals, apply_policy, score_risk


def test_high_risk_captcha_routes_to_review() -> None:
    scored = score_risk(
        RiskSignals(
            job_match_confidence=0.7,
            document_tailoring_confidence=0.8,
            submission_verification_confidence=0.9,
            flags={"captcha_detected"},
        ),
    )
    decision = apply_policy(scored=scored, medium_risk_requires_review=True, manual_override=False)
    assert decision.risk_level == "high_risk"
    assert decision.route_to_review is True
    assert decision.reason == "captcha_detected"


def test_medium_risk_policy_toggle() -> None:
    scored = score_risk(
        RiskSignals(
            job_match_confidence=0.45,
            document_tailoring_confidence=0.5,
            submission_verification_confidence=0.55,
            flags={"low_confidence_match"},
        ),
    )
    routed = apply_policy(scored=scored, medium_risk_requires_review=True, manual_override=False)
    continued = apply_policy(scored=scored, medium_risk_requires_review=False, manual_override=False)

    assert scored.risk_level == "medium_risk"
    assert routed.route_to_review is True
    assert continued.route_to_review is False
