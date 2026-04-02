"""Control-plane basics: tenant plans/overrides and tenant-aware LLM usage.

Revision ID: 20260402_0012
Revises: 20260402_0011
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260402_0012"
down_revision: str | None = "20260402_0011"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tenants", sa.Column("plan_key", sa.String(length=40), nullable=False, server_default="free"))
    op.add_column("tenants", sa.Column("plan_overrides", sa.JSON(), nullable=True))
    op.add_column("tenants", sa.Column("feature_overrides", sa.JSON(), nullable=True))

    op.add_column("llm_usage", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_llm_usage_tenant_created", "llm_usage", ["tenant_id", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_llm_usage_tenant_created", table_name="llm_usage")
    op.drop_column("llm_usage", "tenant_id")

    op.drop_column("tenants", "feature_overrides")
    op.drop_column("tenants", "plan_overrides")
    op.drop_column("tenants", "plan_key")
