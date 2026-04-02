"""Tenant model for multi-tenant SaaS foundations and control-plane settings."""

from sqlalchemy import JSON, Boolean, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Tenant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A logical tenant/workspace owning scoped data."""

    __tablename__ = "tenants"
    __table_args__ = (
        Index("ix_tenant_slug", "slug", unique=True),
        Index("ix_tenant_active", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    plan_key: Mapped[str] = mapped_column(String(40), nullable=False, default="free")
    plan_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    feature_overrides: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug='{self.slug}')>"
