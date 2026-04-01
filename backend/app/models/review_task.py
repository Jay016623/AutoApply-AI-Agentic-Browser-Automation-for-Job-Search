"""Manual review task model for human-in-the-loop decisions."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ReviewTask(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Tenant-scoped review queue task linked to workflow/application context."""

    __tablename__ = "review_tasks"
    __table_args__ = (
        UniqueConstraint("workflow_run_id", "idempotency_key", name="uq_review_task_workflow_idem"),
        Index("ix_review_task_tenant", "tenant_id"),
        Index("ix_review_task_status", "status"),
        Index("ix_review_task_reason", "reason"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    application_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    workflow_run_id: Mapped[str] = mapped_column(String(32), ForeignKey("workflow_runs.id", ondelete="CASCADE"), nullable=False)
    attempt_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("application_attempts.id", ondelete="SET NULL"), nullable=True)

    reason: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="open")
    risk_level: Mapped[str | None] = mapped_column(String(24), nullable=True)
    details_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    resolution_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
