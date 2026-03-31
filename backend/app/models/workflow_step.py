"""Workflow step transition model."""

from sqlalchemy import Boolean, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Transition record for workflow run state changes."""

    __tablename__ = "workflow_steps"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "idempotency_key", name="uq_workflow_step_idempotency"),
        Index("ix_workflow_step_run", "workflow_run_id"),
        Index("ix_workflow_step_to_state", "to_state"),
    )

    workflow_run_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("workflow_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String(80), nullable=False)

    from_state: Mapped[str] = mapped_column(String(40), nullable=False)
    to_state: Mapped[str] = mapped_column(String(40), nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    workflow_run: Mapped["WorkflowRun"] = relationship(back_populates="steps")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<WorkflowStep(run_id={self.workflow_run_id}, "
            f"from={self.from_state}, to={self.to_state})>"
        )
