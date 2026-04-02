"""Workflow run aggregate model."""

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WorkflowRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable pipeline run for a candidate-job pair."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        Index("ix_workflow_run_tenant", "tenant_id"),
        Index("ix_workflow_run_candidate", "candidate_id"),
        Index("ix_workflow_run_state", "current_state"),
    )

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(32), nullable=False)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    current_state: Mapped[str] = mapped_column(String(40), nullable=False, default="discovered")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    steps: Mapped[list["WorkflowStep"]] = relationship(  # noqa: F821
        back_populates="workflow_run",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<WorkflowRun(id={self.id}, candidate_id={self.candidate_id}, "
            f"state='{self.current_state}')>"
        )
