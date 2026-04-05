"""Core execution tenantization for jobs/applications/resumes/settings.

Revision ID: 20260405_0003
Revises: 20260331_0002
Create Date: 2026-04-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260405_0003"
down_revision: str | None = "20260331_0002"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Add tenant ownership columns for core execution entities.

    Nullable-first rollout is used intentionally for backward compatibility.
    A later migration can enforce non-null after staged backfill validation.
    """
    op.add_column("jobs", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_job_tenant", "jobs", ["tenant_id"], unique=False)

    op.add_column("applications", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.add_column(
        "applications",
        sa.Column("execution_task_id", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_application_tenant", "applications", ["tenant_id"], unique=False)
    op.create_index(
        "ix_application_execution_task",
        "applications",
        ["execution_task_id"],
        unique=False,
    )

    op.add_column("resumes", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_resume_tenant", "resumes", ["tenant_id"], unique=False)

    op.add_column("user_settings", sa.Column("tenant_id", sa.String(length=32), nullable=True))
    op.create_index("ix_user_settings_tenant", "user_settings", ["tenant_id"], unique=False)

    # Deterministic backfill path 1: resumes linked to candidates.
    op.execute(
        """
        UPDATE resumes
        SET tenant_id = (
            SELECT c.tenant_id
            FROM candidates c
            WHERE c.id = resumes.candidate_id
        )
        WHERE resumes.tenant_id IS NULL
          AND resumes.candidate_id IS NOT NULL
        """
    )

    # Deterministic backfill path 2: applications linked to resumes.
    op.execute(
        """
        UPDATE applications
        SET tenant_id = (
            SELECT r.tenant_id
            FROM resumes r
            WHERE r.id = applications.resume_id
        )
        WHERE applications.tenant_id IS NULL
          AND applications.resume_id IS NOT NULL
        """
    )

    # Deterministic backfill path 3: applications linked to jobs that already have tenant_id.
    op.execute(
        """
        UPDATE applications
        SET tenant_id = (
            SELECT j.tenant_id
            FROM jobs j
            WHERE j.id = applications.job_id
        )
        WHERE applications.tenant_id IS NULL
          AND applications.job_id IS NOT NULL
        """
    )


def downgrade() -> None:
    """Remove tenant columns introduced for core execution entities."""
    op.drop_index("ix_user_settings_tenant", table_name="user_settings")
    op.drop_column("user_settings", "tenant_id")

    op.drop_index("ix_resume_tenant", table_name="resumes")
    op.drop_column("resumes", "tenant_id")

    op.drop_index("ix_application_execution_task", table_name="applications")
    op.drop_index("ix_application_tenant", table_name="applications")
    op.drop_column("applications", "execution_task_id")
    op.drop_column("applications", "tenant_id")

    op.drop_index("ix_job_tenant", table_name="jobs")
    op.drop_column("jobs", "tenant_id")
