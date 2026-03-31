"""Candidate model for candidate-centric SaaS domain."""

from sqlalchemy import JSON, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Candidate(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A candidate profile container scoped to a tenant."""

    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidate_tenant", "tenant_id"),
        Index("ix_candidate_tenant_email", "tenant_id", "email", unique=True),
        Index("ix_candidate_active", "is_active"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    headline: Mapped[str | None] = mapped_column(String(255), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: {})

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    profile_snapshots: Mapped[list["CandidateProfileSnapshot"]] = relationship(  # noqa: F821
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    resume_versions: Mapped[list["ResumeVersion"]] = relationship(  # noqa: F821
        back_populates="candidate",
        cascade="all, delete-orphan",
    )
    cover_letter_versions: Mapped[list["CoverLetterVersion"]] = relationship(  # noqa: F821
        back_populates="candidate",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Candidate(id={self.id}, email='{self.email}')>"
