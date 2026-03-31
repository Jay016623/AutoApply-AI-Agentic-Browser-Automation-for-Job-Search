"""Tenant model for multi-tenant SaaS foundations."""

from sqlalchemy import Boolean, Index, String
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

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, slug='{self.slug}')>"
