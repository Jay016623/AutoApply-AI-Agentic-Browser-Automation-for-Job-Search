"""Manual checkpoint model for actionable worker blockers."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ManualCheckpoint(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Operator-actionable checkpoint emitted from real execution blockers."""

    __tablename__ = "manual_checkpoints"
    __table_args__ = (
        Index("ix_checkpoint_tenant_status_created", "tenant_id", "status", "created_at"),
        Index("ix_checkpoint_application_created", "application_id", "created_at"),
        Index("ix_checkpoint_attempt_created", "attempt_id", "created_at"),
        Index("ix_checkpoint_type_status", "checkpoint_type", "status"),
    )

    tenant_id: Mapped[str] = mapped_column(String(32), nullable=False)
    application_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("application_attempts.id", ondelete="CASCADE"),
        nullable=False,
    )
    step_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("application_attempt_steps.id", ondelete="SET NULL"),
        nullable=True,
    )

    checkpoint_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    reason_code: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_message: Mapped[str] = mapped_column(Text, nullable=False)
    blocker_confidence: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_to: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
