"""Add users/memberships and hard-tenant scoping columns.

Revision ID: 20260331_0006
Revises: 20260331_0005
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0006"
down_revision: str | None = "20260331_0005"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_email", "users", ["email"], unique=True)
    op.create_index("ix_user_active", "users", ["is_active"], unique=False)

    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("user_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=30), nullable=False, server_default="reviewer"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_tenant_user_membership"),
    )
    op.create_index("ix_membership_user", "tenant_memberships", ["user_id"], unique=False)
    op.create_index("ix_membership_tenant", "tenant_memberships", ["tenant_id"], unique=False)
    op.create_index("ix_membership_role", "tenant_memberships", ["role"], unique=False)

    op.add_column("applications", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_application_tenant", "applications", ["tenant_id"], unique=False)

    op.add_column("resumes", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_resume_tenant", "resumes", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_resume_tenant", table_name="resumes")
    op.drop_column("resumes", "tenant_id")

    op.drop_index("ix_application_tenant", table_name="applications")
    op.drop_column("applications", "tenant_id")

    op.drop_index("ix_membership_role", table_name="tenant_memberships")
    op.drop_index("ix_membership_tenant", table_name="tenant_memberships")
    op.drop_index("ix_membership_user", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")

    op.drop_index("ix_user_active", table_name="users")
    op.drop_index("ix_user_email", table_name="users")
    op.drop_table("users")
