"""Link applications to durable workflow runs.

Revision ID: 20260331_0004
Revises: 20260331_0003
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0004"
down_revision: str | None = "20260331_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("workflow_run_id", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_applications_workflow_run_id",
        "applications",
        "workflow_runs",
        ["workflow_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_applications_workflow_run_id", "applications", type_="foreignkey")
    op.drop_column("applications", "workflow_run_id")
