"""Versioned candidate profile snapshots."""

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CandidateProfileSnapshot(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Immutable snapshot of candidate profile data."""

    __tablename__ = "candidate_profile_snapshots"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_candidate_profile_version"),
        Index("ix_candidate_profile_tenant", "tenant_id"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="manual")

    summary: Mapped[str] = mapped_column(String(4000), nullable=False, default="")
    skills: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    experience: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    education: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    certifications: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    snapshot_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="profile_snapshots")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<CandidateProfileSnapshot(candidate_id={self.candidate_id}, "
            f"version={self.version})>"
        )
