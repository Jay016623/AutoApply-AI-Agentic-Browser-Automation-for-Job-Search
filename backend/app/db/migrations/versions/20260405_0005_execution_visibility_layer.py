"""Execution visibility layer: attempts, steps, proofs, and checkpoints.

Revision ID: 20260405_0005
Revises: 20260405_0004
Create Date: 2026-04-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260405_0005"
down_revision: str | None = "20260405_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add additive execution visibility tables for pilot ops support."""
    op.create_table(
        "application_attempts",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("application_id", sa.String(length=32), nullable=False),
        sa.Column("candidate_id", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("trigger_reason", sa.String(length=80), nullable=True),
        sa.Column("execution_task_id", sa.String(length=32), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("failed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_trace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attempt_tenant_status_created",
        "application_attempts",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attempt_application_created",
        "application_attempts",
        ["application_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attempt_candidate_created",
        "application_attempts",
        ["candidate_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "application_attempt_steps",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=32), nullable=False),
        sa.Column("application_id", sa.String(length=32), nullable=False),
        sa.Column("step_name", sa.String(length=80), nullable=False),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_attempt_step_attempt_order",
        "application_attempt_steps",
        ["attempt_id", "step_order"],
        unique=False,
    )
    op.create_index(
        "ix_attempt_step_tenant_status_created",
        "application_attempt_steps",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_attempt_step_application_created",
        "application_attempt_steps",
        ["application_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "proof_artifacts",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("application_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=32), nullable=False),
        sa.Column("step_id", sa.String(length=32), nullable=True),
        sa.Column("artifact_type", sa.String(length=50), nullable=False),
        sa.Column("storage_uri", sa.String(length=1000), nullable=False),
        sa.Column("content_type", sa.String(length=120), nullable=True),
        sa.Column("checksum", sa.String(length=128), nullable=True),
        sa.Column("captured_at", sa.DateTime(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["application_attempt_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_proof_tenant_created", "proof_artifacts", ["tenant_id", "created_at"], unique=False)
    op.create_index(
        "ix_proof_application_created",
        "proof_artifacts",
        ["application_id", "created_at"],
        unique=False,
    )
    op.create_index("ix_proof_attempt_created", "proof_artifacts", ["attempt_id", "created_at"], unique=False)
    op.create_index("ix_proof_type_created", "proof_artifacts", ["artifact_type", "created_at"], unique=False)

    op.create_table(
        "manual_checkpoints",
        sa.Column("tenant_id", sa.String(length=32), nullable=False),
        sa.Column("application_id", sa.String(length=32), nullable=False),
        sa.Column("attempt_id", sa.String(length=32), nullable=False),
        sa.Column("step_id", sa.String(length=32), nullable=True),
        sa.Column("checkpoint_type", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("reason_code", sa.String(length=80), nullable=False),
        sa.Column("reason_message", sa.Text(), nullable=False),
        sa.Column("blocker_confidence", sa.String(length=20), nullable=True),
        sa.Column("assigned_to", sa.String(length=64), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["application_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["step_id"], ["application_attempt_steps.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_checkpoint_tenant_status_created",
        "manual_checkpoints",
        ["tenant_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_checkpoint_application_created",
        "manual_checkpoints",
        ["application_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_checkpoint_attempt_created",
        "manual_checkpoints",
        ["attempt_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_checkpoint_type_status",
        "manual_checkpoints",
        ["checkpoint_type", "status"],
        unique=False,
    )


def downgrade() -> None:
    """Drop execution visibility tables."""
    op.drop_index("ix_checkpoint_type_status", table_name="manual_checkpoints")
    op.drop_index("ix_checkpoint_attempt_created", table_name="manual_checkpoints")
    op.drop_index("ix_checkpoint_application_created", table_name="manual_checkpoints")
    op.drop_index("ix_checkpoint_tenant_status_created", table_name="manual_checkpoints")
    op.drop_table("manual_checkpoints")

    op.drop_index("ix_proof_type_created", table_name="proof_artifacts")
    op.drop_index("ix_proof_attempt_created", table_name="proof_artifacts")
    op.drop_index("ix_proof_application_created", table_name="proof_artifacts")
    op.drop_index("ix_proof_tenant_created", table_name="proof_artifacts")
    op.drop_table("proof_artifacts")

    op.drop_index("ix_attempt_step_application_created", table_name="application_attempt_steps")
    op.drop_index("ix_attempt_step_tenant_status_created", table_name="application_attempt_steps")
    op.drop_index("ix_attempt_step_attempt_order", table_name="application_attempt_steps")
    op.drop_table("application_attempt_steps")

    op.drop_index("ix_attempt_candidate_created", table_name="application_attempts")
    op.drop_index("ix_attempt_application_created", table_name="application_attempts")
    op.drop_index("ix_attempt_tenant_status_created", table_name="application_attempts")
    op.drop_table("application_attempts")
