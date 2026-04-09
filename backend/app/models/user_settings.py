"""User settings database model."""

from sqlalchemy import JSON, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, generate_uuid


class UserSettings(TimestampMixin, Base):
    """User preferences and configuration keyed by tenant."""

    __tablename__ = "user_settings"
    __table_args__ = (
        Index("ix_user_settings_tenant", "tenant_id"),
        UniqueConstraint("tenant_id", name="uq_user_settings_tenant"),
    )

    id: Mapped[str] = mapped_column(
        String(32),
        primary_key=True,
        default=generate_uuid,
    )

    tenant_id: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Application behavior
    apply_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="review")
    max_parallel: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    min_ats_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.75)

    # LLM preferences
    preferred_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="openai")

    # Platform config
    platforms_enabled: Mapped[list] = mapped_column(
        JSON,
        nullable=False,
        default=lambda: ["linkedin", "indeed", "glassdoor"],
    )

    # Candidate profile
    candidate_profile: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<UserSettings(apply_mode='{self.apply_mode}', "
            f"provider='{self.preferred_provider}')>"
        )
