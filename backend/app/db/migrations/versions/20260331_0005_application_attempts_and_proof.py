"""Add application attempts, step checkpoints, and proof artifacts.

Revision ID: 20260331_0005
Revises: 20260331_0004
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0005"
down_revision: str | None = "20260331_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "application_attempts",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("application_id", sa.String(length=32), nullable=False),
        sa.Column("workflow_run_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=True),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("current_step", sa.String(length=80), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=80), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("manual_checkpoint_required", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("manual_checkpoint_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("application_id", "idempotency_key", name="uq_attempt_application_idempotency"),
    )
    op.create_index("ix_attempt_tenant", "application_attempts", ["tenant_id"], unique=False)
    op.create_index("ix_attempt_application", "application_attempts", ["application_id"], unique=False)
    op.create_index("ix_attempt_status", "application_attempts", ["status"], unique=False)

    op.create_table(
        "application_attempt_steps",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("attempt_id", sa.String(length=32), nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="pending"),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("output_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "idempotency_key", name="uq_attempt_step_idempotency"),
        sa.UniqueConstraint("attempt_id", "sequence_number", name="uq_attempt_step_sequence"),
    )
    op.create_index("ix_attempt_step_tenant", "application_attempt_steps", ["tenant_id"], unique=False)
    op.create_index("ix_attempt_step_attempt", "application_attempt_steps", ["attempt_id"], unique=False)
    op.create_index("ix_attempt_step_status", "application_attempt_steps", ["status"], unique=False)

    op.create_table(
        "proof_artifacts",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("application_id", sa.String(length=32), nullable=True),
        sa.Column("workflow_run_id", sa.String(length=32), nullable=True),
        sa.Column("attempt_id", sa.String(length=32), nullable=True),
        sa.Column("attempt_step_id", sa.String(length=32), nullable=True),
        sa.Column("artifact_type", sa.String(length=40), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["attempt_step_id"], ["application_attempt_steps.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proof_tenant", "proof_artifacts", ["tenant_id"], unique=False)
    op.create_index("ix_proof_application", "proof_artifacts", ["application_id"], unique=False)
    op.create_index("ix_proof_attempt", "proof_artifacts", ["attempt_id"], unique=False)
    op.create_index("ix_proof_type", "proof_artifacts", ["artifact_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_proof_type", table_name="proof_artifacts")
    op.drop_index("ix_proof_attempt", table_name="proof_artifacts")
    op.drop_index("ix_proof_application", table_name="proof_artifacts")
    op.drop_index("ix_proof_tenant", table_name="proof_artifacts")
    op.drop_table("proof_artifacts")

    op.drop_index("ix_attempt_step_status", table_name="application_attempt_steps")
    op.drop_index("ix_attempt_step_attempt", table_name="application_attempt_steps")
    op.drop_index("ix_attempt_step_tenant", table_name="application_attempt_steps")
    op.drop_table("application_attempt_steps")

    op.drop_index("ix_attempt_status", table_name="application_attempts")
    op.drop_index("ix_attempt_application", table_name="application_attempts")
    op.drop_index("ix_attempt_tenant", table_name="application_attempts")
    op.drop_table("application_attempts")
