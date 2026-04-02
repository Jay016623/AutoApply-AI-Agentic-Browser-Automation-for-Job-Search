"""Versioned cover letter artifacts linked to a candidate."""

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class CoverLetterVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned cover letter generated for a candidate/job."""

    __tablename__ = "cover_letter_versions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_cover_letter_version"),
        Index("ix_cover_letter_version_tenant", "tenant_id"),
        Index("ix_cover_letter_version_candidate", "candidate_id"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="Cover Letter")
    template_id: Mapped[str] = mapped_column(String(50), nullable=False, default="standard")

    file_path_pdf: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_path_docx: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="cover_letter_versions")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<CoverLetterVersion(candidate_id={self.candidate_id}, "
            f"version={self.version})>"
        )
