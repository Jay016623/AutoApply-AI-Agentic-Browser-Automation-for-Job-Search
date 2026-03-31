"""Proof artifacts captured during application execution."""

from sqlalchemy import JSON, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProofArtifact(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Execution artifact linked to application/workflow/attempt context."""

    __tablename__ = "proof_artifacts"
    __table_args__ = (
        Index("ix_proof_tenant", "tenant_id"),
        Index("ix_proof_application", "application_id"),
        Index("ix_proof_attempt", "attempt_id"),
        Index("ix_proof_type", "artifact_type"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    application_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("workflow_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("application_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    attempt_step_id: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("application_attempt_steps.id", ondelete="SET NULL"),
        nullable=True,
    )

    artifact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    checksum: Mapped[str | None] = mapped_column(String(128), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    attempt: Mapped["ApplicationAttempt | None"] = relationship(back_populates="proof_artifacts")  # noqa: F821
    attempt_step: Mapped["ApplicationAttemptStep | None"] = relationship(back_populates="proof_artifacts")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ProofArtifact(id={self.id}, type={self.artifact_type}, path='{self.storage_path}')>"
