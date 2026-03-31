"""Application workflow state and transition skeletons.

Phase 1 intentionally introduces state definitions and transition guards
without replacing existing business pipelines.
"""

from dataclasses import dataclass
from enum import StrEnum


class ApplicationWorkflowState(StrEnum):
    """Canonical workflow states for durable, resumable processing."""

    CREATED = "created"
    QUEUED = "queued"
    APPROVED = "approved"
    DISCOVERY_PENDING = "discovery_pending"
    MATCHING_PENDING = "matching_pending"
    TAILORING_PENDING = "tailoring_pending"
    APPLY_PENDING = "apply_pending"
    APPLYING = "applying"
    APPLIED = "applied"
    MANUAL_CHECKPOINT = "manual_checkpoint"
    FAILED = "failed"
    CANCELLED = "cancelled"


_ALLOWED_TRANSITIONS: dict[ApplicationWorkflowState, set[ApplicationWorkflowState]] = {
    ApplicationWorkflowState.CREATED: {
        ApplicationWorkflowState.QUEUED,
        ApplicationWorkflowState.CANCELLED,
    },
    ApplicationWorkflowState.QUEUED: {
        ApplicationWorkflowState.APPROVED,
        ApplicationWorkflowState.CANCELLED,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.APPROVED: {
        ApplicationWorkflowState.DISCOVERY_PENDING,
        ApplicationWorkflowState.MATCHING_PENDING,
        ApplicationWorkflowState.TAILORING_PENDING,
        ApplicationWorkflowState.APPLY_PENDING,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
    },
    ApplicationWorkflowState.DISCOVERY_PENDING: {
        ApplicationWorkflowState.MATCHING_PENDING,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.MATCHING_PENDING: {
        ApplicationWorkflowState.TAILORING_PENDING,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.TAILORING_PENDING: {
        ApplicationWorkflowState.APPLY_PENDING,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.APPLY_PENDING: {
        ApplicationWorkflowState.APPLYING,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.APPLYING: {
        ApplicationWorkflowState.APPLIED,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.FAILED,
    },
    ApplicationWorkflowState.MANUAL_CHECKPOINT: {
        ApplicationWorkflowState.APPLY_PENDING,
        ApplicationWorkflowState.APPLYING,
        ApplicationWorkflowState.CANCELLED,
    },
    ApplicationWorkflowState.APPLIED: set(),
    ApplicationWorkflowState.FAILED: {
        ApplicationWorkflowState.QUEUED,
        ApplicationWorkflowState.MANUAL_CHECKPOINT,
        ApplicationWorkflowState.CANCELLED,
    },
    ApplicationWorkflowState.CANCELLED: set(),
}


@dataclass(frozen=True)
class WorkflowTransitionResult:
    """Outcome of a requested transition."""

    allowed: bool
    from_state: ApplicationWorkflowState
    to_state: ApplicationWorkflowState
    reason: str = ""


def get_next_states(state: ApplicationWorkflowState) -> set[ApplicationWorkflowState]:
    """Return all valid next states for the given state."""
    return _ALLOWED_TRANSITIONS.get(state, set())


def can_transition(
    current: ApplicationWorkflowState,
    target: ApplicationWorkflowState,
) -> bool:
    """Check whether a transition is allowed."""
    return target in get_next_states(current)


def transition(
    current: ApplicationWorkflowState,
    target: ApplicationWorkflowState,
) -> WorkflowTransitionResult:
    """Validate a transition and return a descriptive result."""
    if can_transition(current, target):
        return WorkflowTransitionResult(True, current, target)

    if current == target:
        reason = "no_op_transition"
    elif target in (ApplicationWorkflowState.APPLIED, ApplicationWorkflowState.APPLYING):
        reason = "unsafe_direct_apply_transition"
    else:
        reason = "invalid_transition"

    return WorkflowTransitionResult(
        allowed=False,
        from_state=current,
        to_state=target,
        reason=reason,
    )
