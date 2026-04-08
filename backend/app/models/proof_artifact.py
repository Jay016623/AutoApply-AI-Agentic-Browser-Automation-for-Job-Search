"""Proof artifact model for execution evidence."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProofArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Persisted evidence produced by real execution runtime."""

    __tablename__ = "proof_artifacts"
    __table_args__ = (
        Index("ix_proof_tenant_created", "tenant_id", "created_at"),
        Index("ix_proof_application_created", "application_id", "created_at"),
        Index("ix_proof_attempt_created", "attempt_id", "created_at"),
        Index("ix_proof_type_created", "artifact_type", "created_at"),
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

    artifact_type: Mapped[str] = mapped_column(String(50), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
