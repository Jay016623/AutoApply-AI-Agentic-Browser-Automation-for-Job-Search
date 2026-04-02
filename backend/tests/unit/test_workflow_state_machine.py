"""Unit tests for workflow transition and retry semantics."""

import pytest

from app.domains.applications.workflow.retry_policy import evaluate_retry, exponential_backoff_delay
from app.domains.applications.workflow.states import (
    WorkflowState,
    can_transition,
    get_next_states,
    transition,
)


class TestWorkflowStateMachine:
    """Validate allowed/blocked workflow transitions."""

    def test_happy_path_transitions(self) -> None:
        next_states = get_next_states(WorkflowState.DISCOVERED)
        assert WorkflowState.MATCHED in next_states

        result = transition(WorkflowState.MATCHED, WorkflowState.SHORTLISTED)
        assert result.allowed is True

    def test_submit_requires_applying(self) -> None:
        result = transition(WorkflowState.READY_TO_APPLY, WorkflowState.SUBMITTED)
        assert result.allowed is False
        assert result.reason == "submit_requires_applying"

    def test_terminal_state_blocks_transitions(self) -> None:
        assert not can_transition(WorkflowState.SUBMITTED, WorkflowState.APPLYING)

    def test_idempotent_same_state_is_allowed_noop(self) -> None:
        result = transition(WorkflowState.MATCHED, WorkflowState.MATCHED)
        assert result.allowed is True
        assert result.reason == "idempotent_noop"


class TestRetryPolicy:
    """Validate retry policy decisions."""

    @pytest.mark.parametrize(
        ("attempt", "expected"),
        [
            (1, 5),
            (2, 10),
            (3, 20),
            (10, 300),
        ],
    )
    def test_exponential_backoff_is_bounded(self, attempt: int, expected: int) -> None:
        assert exponential_backoff_delay(attempt) == expected

    def test_retry_decision_for_retryable_failure(self) -> None:
        decision = evaluate_retry(WorkflowState.FAILED_RETRYABLE, retry_count=1, max_retries=3)
        assert decision.retryable is True
        assert decision.next_attempt == 2
        assert decision.reason == "retry_scheduled"

    def test_retry_decision_when_exhausted(self) -> None:
        decision = evaluate_retry(WorkflowState.FAILED_RETRYABLE, retry_count=3, max_retries=3)
        assert decision.retryable is False
        assert decision.reason == "max_retries_exceeded"
