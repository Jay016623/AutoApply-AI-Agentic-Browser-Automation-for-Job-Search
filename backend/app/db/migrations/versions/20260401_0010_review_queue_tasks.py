"""Add review queue task model for human-in-the-loop workflow.

Revision ID: 20260401_0010
Revises: 20260401_0009
Create Date: 2026-04-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260401_0010"
down_revision: str | None = "20260401_0009"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("application_id", sa.String(length=32), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=32), nullable=True),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False, server_default="open"),
        sa.Column("risk_level", sa.String(length=24), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=True),
        sa.Column("resolution_action", sa.String(length=32), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("resolved_by", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "idempotency_key", name="uq_review_task_workflow_idem"),
    )
    op.create_index("ix_review_task_tenant", "review_tasks", ["tenant_id"], unique=False)
    op.create_index("ix_review_task_status", "review_tasks", ["status"], unique=False)
    op.create_index("ix_review_task_reason", "review_tasks", ["reason"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_review_task_reason", table_name="review_tasks")
    op.drop_index("ix_review_task_status", table_name="review_tasks")
    op.drop_index("ix_review_task_tenant", table_name="review_tasks")
    op.drop_table("review_tasks")
