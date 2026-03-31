"""Phase 1 foundations: tenants + audit logs.

Revision ID: 20260331_0001
Revises:
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260331_0001"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Create Phase 1 foundation tables."""
    op.create_table(
        "tenants",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tenant_slug", "tenants", ["slug"], unique=True)
    op.create_index("ix_tenant_active", "tenants", ["is_active"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("actor_type", sa.String(length=30), nullable=False, server_default="system"),
        sa.Column("entity_type", sa.String(length=80), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="recorded"),
        sa.Column("message", sa.Text(), nullable=False, server_default=""),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_entity", "audit_logs", ["entity_type", "entity_id"], unique=False)
    op.create_index("ix_audit_event", "audit_logs", ["event_type"], unique=False)
    op.create_index(
        "ix_audit_tenant_created",
        "audit_logs",
        ["tenant_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop Phase 1 foundation tables."""
    op.drop_index("ix_audit_tenant_created", table_name="audit_logs")
    op.drop_index("ix_audit_event", table_name="audit_logs")
    op.drop_index("ix_audit_entity", table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index("ix_tenant_active", table_name="tenants")
    op.drop_index("ix_tenant_slug", table_name="tenants")
    op.drop_table("tenants")
