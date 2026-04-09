"""Application execution attempt model."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single worker execution attempt for an application."""

    __tablename__ = "application_attempts"
    __table_args__ = (
        Index("ix_attempt_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_attempt_application_created", "application_id", "created_at"),
        Index("ix_attempt_candidate_created", "candidate_id", "created_at"),
    )

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    application_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    trigger_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    execution_task_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    worker_trace_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    application: Mapped["Application"] = relationship(backref="attempts")  # noqa: F821
    steps: Mapped[list["ApplicationAttemptStep"]] = relationship(  # noqa: F821
        back_populates="attempt",
        cascade="all, delete-orphan",
    )
