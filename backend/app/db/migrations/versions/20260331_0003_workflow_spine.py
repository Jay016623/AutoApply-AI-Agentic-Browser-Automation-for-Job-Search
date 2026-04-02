"""Workflow orchestration spine tables.

Revision ID: 20260331_0003
Revises: 20260331_0002
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0003"
down_revision: str | None = "20260331_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("current_state", sa.String(length=40), nullable=False, server_default="discovered"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_run_tenant", "workflow_runs", ["tenant_id"], unique=False)
    op.create_index("ix_workflow_run_candidate", "workflow_runs", ["candidate_id"], unique=False)
    op.create_index("ix_workflow_run_state", "workflow_runs", ["current_state"], unique=False)

    op.create_table(
        "workflow_steps",
        sa.Column("workflow_run_id", sa.String(length=32), nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("from_state", sa.String(length=40), nullable=False),
        sa.Column("to_state", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="completed"),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(length=100), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workflow_run_id", "idempotency_key", name="uq_workflow_step_idempotency"),
    )
    op.create_index("ix_workflow_step_run", "workflow_steps", ["workflow_run_id"], unique=False)
    op.create_index("ix_workflow_step_to_state", "workflow_steps", ["to_state"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_workflow_step_to_state", table_name="workflow_steps")
    op.drop_index("ix_workflow_step_run", table_name="workflow_steps")
    op.drop_table("workflow_steps")

    op.drop_index("ix_workflow_run_state", table_name="workflow_runs")
    op.drop_index("ix_workflow_run_candidate", table_name="workflow_runs")
    op.drop_index("ix_workflow_run_tenant", table_name="workflow_runs")
    op.drop_table("workflow_runs")
