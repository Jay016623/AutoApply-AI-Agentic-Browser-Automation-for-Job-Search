"""Durable application execution attempt model."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationAttempt(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A replay-safe execution attempt for a single application."""

    __tablename__ = "application_attempts"
    __table_args__ = (
        UniqueConstraint("application_id", "idempotency_key", name="uq_attempt_application_idempotency"),
        Index("ix_attempt_tenant", "tenant_id"),
        Index("ix_attempt_application", "application_id"),
        Index("ix_attempt_status", "status"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    application_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    candidate_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    current_step: Mapped[str | None] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    last_error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    manual_checkpoint_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    manual_checkpoint_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    steps: Mapped[list["ApplicationAttemptStep"]] = relationship(  # noqa: F821
        back_populates="attempt",
        cascade="all, delete-orphan",
    )
    proof_artifacts: Mapped[list["ProofArtifact"]] = relationship(  # noqa: F821
        back_populates="attempt",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ApplicationAttempt(id={self.id}, application_id={self.application_id}, status='{self.status}')>"
