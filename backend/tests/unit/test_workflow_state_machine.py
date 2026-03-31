"""Unit tests for workflow transition skeletons."""

from app.domains.applications.workflow.states import (
    ApplicationWorkflowState,
    can_transition,
    get_next_states,
    transition,
)


class TestWorkflowStateMachine:
    """Validate allowed/blocked workflow transitions."""

    def test_next_states_for_approved_include_apply_pipeline(self) -> None:
        next_states = get_next_states(ApplicationWorkflowState.APPROVED)
        assert ApplicationWorkflowState.APPLY_PENDING in next_states
        assert ApplicationWorkflowState.MANUAL_CHECKPOINT in next_states

    def test_valid_transition_returns_allowed(self) -> None:
        result = transition(
            ApplicationWorkflowState.APPLY_PENDING,
            ApplicationWorkflowState.APPLYING,
        )
        assert result.allowed is True
        assert result.reason == ""

    def test_invalid_transition_to_applied_is_blocked(self) -> None:
        result = transition(
            ApplicationWorkflowState.QUEUED,
            ApplicationWorkflowState.APPLIED,
        )
        assert result.allowed is False
        assert result.reason == "unsafe_direct_apply_transition"

    def test_can_transition_false_for_terminal_states(self) -> None:
        assert not can_transition(
            ApplicationWorkflowState.APPLIED,
            ApplicationWorkflowState.QUEUED,
        )
