"""Tenant-scope jobs and enforce tenant-platform uniqueness.

Revision ID: 20260331_0007
Revises: 20260331_0006
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0007"
down_revision: str | None = "20260331_0006"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.add_column(sa.Column("tenant_id", sa.String(length=32), nullable=True))
        batch_op.create_index("ix_job_tenant", ["tenant_id"], unique=False)
        batch_op.drop_constraint("uq_job_platform_id", type_="unique")
        batch_op.create_unique_constraint(
            "uq_job_tenant_platform_id",
            ["tenant_id", "platform", "platform_job_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_constraint("uq_job_tenant_platform_id", type_="unique")
        batch_op.create_unique_constraint("uq_job_platform_id", ["platform", "platform_job_id"])
        batch_op.drop_index("ix_job_tenant")
        batch_op.drop_column("tenant_id")
