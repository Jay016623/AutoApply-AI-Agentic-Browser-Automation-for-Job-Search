"""Phase 1 strict tenant backfill and high-value NOT NULL hardening.

Revision ID: 20260402_0011
Revises: 20260401_0010
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260402_0011"
down_revision: str | None = "20260401_0010"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def _null_count(table: str) -> int:
    bind = op.get_bind()
    return int(bind.execute(sa.text(f"SELECT COUNT(1) FROM {table} WHERE tenant_id IS NULL")).scalar() or 0)


def upgrade() -> None:
    # Safe backfill propagation from known ownership paths.
    op.execute(
        sa.text(
            """
            UPDATE jobs
            SET tenant_id = (
                SELECT a.tenant_id
                FROM applications a
                WHERE a.job_id = jobs.id AND a.tenant_id IS NOT NULL
                LIMIT 1
            )
            WHERE jobs.tenant_id IS NULL
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE applications
            SET tenant_id = (
                SELECT j.tenant_id FROM jobs j WHERE j.id = applications.job_id
            )
            WHERE applications.tenant_id IS NULL
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE workflow_runs
            SET tenant_id = (
                SELECT a.tenant_id
                FROM applications a
                WHERE a.workflow_run_id = workflow_runs.id AND a.tenant_id IS NOT NULL
                LIMIT 1
            )
            WHERE workflow_runs.tenant_id IS NULL
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE application_attempts
            SET tenant_id = (
                SELECT a.tenant_id FROM applications a WHERE a.id = application_attempts.application_id
            )
            WHERE application_attempts.tenant_id IS NULL
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE proof_artifacts
            SET tenant_id = (
                SELECT at.tenant_id FROM application_attempts at WHERE at.id = proof_artifacts.attempt_id
            )
            WHERE proof_artifacts.tenant_id IS NULL
            """,
        ),
    )
    op.execute(
        sa.text(
            """
            UPDATE review_tasks
            SET tenant_id = (
                SELECT wr.tenant_id FROM workflow_runs wr WHERE wr.id = review_tasks.workflow_run_id
            )
            WHERE review_tasks.tenant_id IS NULL
            """,
        ),
    )

    critical_tables = [
        "applications",
        "workflow_runs",
        "application_attempts",
        "proof_artifacts",
        "review_tasks",
    ]
    unresolved = {table: _null_count(table) for table in critical_tables}
    violations = {k: v for k, v in unresolved.items() if v > 0}
    if violations:
        raise RuntimeError(f"tenant_backfill_incomplete_for_strict_phase1:{violations}")

    op.alter_column("applications", "tenant_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("workflow_runs", "tenant_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("application_attempts", "tenant_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("proof_artifacts", "tenant_id", existing_type=sa.String(length=32), nullable=False)
    op.alter_column("review_tasks", "tenant_id", existing_type=sa.String(length=32), nullable=False)


def downgrade() -> None:
    op.alter_column("review_tasks", "tenant_id", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("proof_artifacts", "tenant_id", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("application_attempts", "tenant_id", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("workflow_runs", "tenant_id", existing_type=sa.String(length=32), nullable=True)
    op.alter_column("applications", "tenant_id", existing_type=sa.String(length=32), nullable=True)
