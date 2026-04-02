"""Contract tests for execution schema/failure taxonomy stability."""

from app.domains.applications.execution.adapters import FailureCategory


def test_failure_taxonomy_contract_values() -> None:
    expected = {
        "timeout",
        "auth_expired",
        "captcha",
        "selector_drift",
        "upload_failed",
        "duplicate_application",
        "unsupported_ui",
        "unknown",
    }
    assert {item.value for item in FailureCategory} == expected
