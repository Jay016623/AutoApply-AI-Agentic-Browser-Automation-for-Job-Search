"""Application attempt step persistence model."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ApplicationAttemptStep(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A durable step execution record for one application attempt."""

    __tablename__ = "application_attempt_steps"
    __table_args__ = (
        UniqueConstraint("attempt_id", "idempotency_key", name="uq_attempt_step_idempotency"),
        UniqueConstraint("attempt_id", "sequence_number", name="uq_attempt_step_sequence"),
        Index("ix_attempt_step_tenant", "tenant_id"),
        Index("ix_attempt_step_attempt", "attempt_id"),
        Index("ix_attempt_step_status", "status"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    attempt_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("application_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_name: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    input_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_snapshot_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)

    attempt: Mapped["ApplicationAttempt"] = relationship(back_populates="steps")  # noqa: F821
    proof_artifacts: Mapped[list["ProofArtifact"]] = relationship(  # noqa: F821
        back_populates="attempt_step",
    )

    @property
    def proof_artifact_count(self) -> int:
        return len(self.proof_artifacts or [])

    def __repr__(self) -> str:
        return f"<ApplicationAttemptStep(id={self.id}, attempt_id={self.attempt_id}, step='{self.step_name}')>"
