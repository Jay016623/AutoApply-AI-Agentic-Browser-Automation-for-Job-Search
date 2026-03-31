"""Versioned resume artifacts linked to a candidate."""

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ResumeVersion(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A versioned resume artifact generated or uploaded for a candidate."""

    __tablename__ = "resume_versions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version", name="uq_resume_version"),
        Index("ix_resume_version_tenant", "tenant_id"),
        Index("ix_resume_version_candidate", "candidate_id"),
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    candidate_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
    )
    resume_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    version: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="Resume")
    template_id: Mapped[str] = mapped_column(String(50), nullable=False, default="modern")
    variant_type: Mapped[str] = mapped_column(String(30), nullable=False, default="base")

    file_path_pdf: Mapped[str | None] = mapped_column(String(500), nullable=True)
    file_path_docx: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    ats_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    candidate: Mapped["Candidate"] = relationship(back_populates="resume_versions")  # noqa: F821

    def __repr__(self) -> str:
        return f"<ResumeVersion(candidate_id={self.candidate_id}, version={self.version})>"
