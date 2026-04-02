"""Retry policy helpers for workflow transitions."""

from dataclasses import dataclass

from app.domains.applications.workflow.states import WorkflowState


@dataclass(frozen=True)
class RetryDecision:
    """Decision payload for retry scheduling."""

    retryable: bool
    next_attempt: int
    delay_seconds: int
    reason: str


def exponential_backoff_delay(
    attempt: int,
    base_delay_seconds: int = 5,
    max_delay_seconds: int = 300,
) -> int:
    """Compute bounded exponential backoff delay."""
    if attempt <= 0:
        return base_delay_seconds
    delay = base_delay_seconds * (2 ** (attempt - 1))
    return min(delay, max_delay_seconds)


def evaluate_retry(
    state: WorkflowState,
    retry_count: int,
    max_retries: int,
) -> RetryDecision:
    """Evaluate whether a failed run can be retried."""
    if state != WorkflowState.FAILED_RETRYABLE:
        return RetryDecision(
            retryable=False,
            next_attempt=retry_count,
            delay_seconds=0,
            reason="state_not_retryable",
        )

    next_attempt = retry_count + 1
    if next_attempt > max_retries:
        return RetryDecision(
            retryable=False,
            next_attempt=retry_count,
            delay_seconds=0,
            reason="max_retries_exceeded",
        )

    return RetryDecision(
        retryable=True,
        next_attempt=next_attempt,
        delay_seconds=exponential_backoff_delay(next_attempt),
        reason="retry_scheduled",
    )
