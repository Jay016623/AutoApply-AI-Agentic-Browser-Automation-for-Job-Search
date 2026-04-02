"""Durable workflow states and transition rules for candidate job pipeline."""

from dataclasses import dataclass
from enum import StrEnum


class WorkflowState(StrEnum):
    """Canonical workflow states for pipeline orchestration."""

    DISCOVERED = "discovered"
    MATCHED = "matched"
    SHORTLISTED = "shortlisted"
    TAILORED = "tailored"
    READY_TO_APPLY = "ready_to_apply"
    APPLYING = "applying"
    SUBMITTED = "submitted"
    FAILED_RETRYABLE = "failed_retryable"
    FAILED_MANUAL = "failed_manual"
    ABANDONED = "abandoned"


# Backward-compatible alias retained from Phase 1 skeleton.
ApplicationWorkflowState = WorkflowState


_ALLOWED_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.DISCOVERED: {
        WorkflowState.MATCHED,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.MATCHED: {
        WorkflowState.SHORTLISTED,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.SHORTLISTED: {
        WorkflowState.TAILORED,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.TAILORED: {
        WorkflowState.READY_TO_APPLY,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.READY_TO_APPLY: {
        WorkflowState.APPLYING,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.APPLYING: {
        WorkflowState.SUBMITTED,
        WorkflowState.FAILED_RETRYABLE,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.FAILED_RETRYABLE: {
        WorkflowState.APPLYING,
        WorkflowState.FAILED_MANUAL,
        WorkflowState.ABANDONED,
    },
    WorkflowState.FAILED_MANUAL: {
        WorkflowState.READY_TO_APPLY,
        WorkflowState.ABANDONED,
    },
    WorkflowState.SUBMITTED: set(),
    WorkflowState.ABANDONED: set(),
}


@dataclass(frozen=True)
class WorkflowTransitionResult:
    """Outcome of a requested state transition."""

    allowed: bool
    from_state: WorkflowState
    to_state: WorkflowState
    reason: str = ""


def get_next_states(state: WorkflowState) -> set[WorkflowState]:
    """Return allowed next states for current state."""
    return _ALLOWED_TRANSITIONS.get(state, set())


def can_transition(current: WorkflowState, target: WorkflowState) -> bool:
    """Check transition validity."""
    return target in get_next_states(current)


def transition(current: WorkflowState, target: WorkflowState) -> WorkflowTransitionResult:
    """Validate a transition and provide machine-readable reason."""
    if current == target:
        return WorkflowTransitionResult(
            allowed=True,
            from_state=current,
            to_state=target,
            reason="idempotent_noop",
        )

    if can_transition(current, target):
        return WorkflowTransitionResult(True, current, target)

    reason = "invalid_transition"
    if target == WorkflowState.SUBMITTED and current != WorkflowState.APPLYING:
        reason = "submit_requires_applying"

    return WorkflowTransitionResult(False, current, target, reason=reason)
