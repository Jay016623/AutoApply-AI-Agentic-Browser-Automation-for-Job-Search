"""Application execution attempt step model."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationAttemptStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A concrete step entered during an application execution attempt."""

    __tablename__ = "application_attempt_steps"
    __table_args__ = (
        Index("ix_attempt_step_attempt_order", "attempt_id", "step_order"),
        Index("ix_attempt_step_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_attempt_step_application_created", "application_id", "created_at"),
    )

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("application_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    application_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )

    step_name: Mapped[str] = mapped_column(String(80), nullable=False)
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    attempt: Mapped["ApplicationAttempt"] = relationship(back_populates="steps")  # noqa: F821
