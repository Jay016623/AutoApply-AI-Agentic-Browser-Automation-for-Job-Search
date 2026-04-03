"""Add tenant scope columns for jobs and applications.

Revision ID: 20260403_0003
Revises: 20260331_0002
Create Date: 2026-04-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260403_0003"
down_revision: str | None = "20260331_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add tenant_id columns used for incremental tenant scoping rollout."""
    op.add_column("jobs", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_job_tenant", "jobs", ["tenant_id"], unique=False)

    op.add_column("applications", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_application_tenant", "applications", ["tenant_id"], unique=False)

    # Backfill applications from related jobs for better default scoping.
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE applications
            SET tenant_id = (
                SELECT jobs.tenant_id
                FROM jobs
                WHERE jobs.id = applications.job_id
            )
            WHERE tenant_id IS NULL
            """
        ),
    )


def downgrade() -> None:
    """Remove tenant scope columns."""
    op.drop_index("ix_application_tenant", table_name="applications")
    op.drop_column("applications", "tenant_id")

    op.drop_index("ix_job_tenant", table_name="jobs")
    op.drop_column("jobs", "tenant_id")
