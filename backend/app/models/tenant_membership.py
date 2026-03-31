"""Tenant membership and role binding for users."""

from sqlalchemy import ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class TenantMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user_membership"),
        Index("ix_membership_user", "user_id"),
        Index("ix_membership_tenant", "tenant_id"),
        Index("ix_membership_role", "role"),
    )

    tenant_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(30), nullable=False, default="reviewer")
