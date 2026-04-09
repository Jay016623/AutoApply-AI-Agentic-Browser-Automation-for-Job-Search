"""Pilot hardening: settings tenancy + tenant-aligned job uniqueness.

Revision ID: 20260405_0004
Revises: 20260405_0003
Create Date: 2026-04-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260405_0004"
down_revision: str | None = "20260405_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    """Harden constraints with safe additive posture.

    Notes:
    - user_settings moves away from singleton-check semantics; tenant_id becomes
      a unique key for tenant-scoped settings rows.
    - jobs uniqueness is aligned to tenant-aware keys.
    - tenant_id columns remain nullable for backward compatibility in this batch.
      A future migration can enforce non-null after verified backfill.
    """
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # user_settings: remove singleton check and add tenant uniqueness
    # ------------------------------------------------------------------
    check_names = {
        c.get("name")
        for c in inspector.get_check_constraints("user_settings")
        if c.get("name")
    }
    if "ck_user_settings_singleton" in check_names:
        op.drop_constraint(
            "ck_user_settings_singleton",
            "user_settings",
            type_="check",
        )

    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.alter_column(
            "id",
            existing_type=sa.String(length=20),
            type_=sa.String(length=32),
            existing_nullable=False,
        )

    unique_names = {
        c.get("name")
        for c in inspector.get_unique_constraints("user_settings")
        if c.get("name")
    }
    if "uq_user_settings_tenant" not in unique_names:
        op.create_unique_constraint(
            "uq_user_settings_tenant",
            "user_settings",
            ["tenant_id"],
        )

    # ------------------------------------------------------------------
    # jobs: replace global uniqueness with tenant-aware uniqueness
    # ------------------------------------------------------------------
    job_unique_names = {
        c.get("name")
        for c in inspector.get_unique_constraints("jobs")
        if c.get("name")
    }
    if "uq_job_platform_id" in job_unique_names:
        op.drop_constraint("uq_job_platform_id", "jobs", type_="unique")
    if "uq_job_tenant_platform_id" not in job_unique_names:
        op.create_unique_constraint(
            "uq_job_tenant_platform_id",
            "jobs",
            ["tenant_id", "platform", "platform_job_id"],
        )


def downgrade() -> None:
    """Revert pilot hardening constraints."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    job_unique_names = {
        c.get("name")
        for c in inspector.get_unique_constraints("jobs")
        if c.get("name")
    }
    if "uq_job_tenant_platform_id" in job_unique_names:
        op.drop_constraint("uq_job_tenant_platform_id", "jobs", type_="unique")
    if "uq_job_platform_id" not in job_unique_names:
        op.create_unique_constraint(
            "uq_job_platform_id",
            "jobs",
            ["platform", "platform_job_id"],
        )

    unique_names = {
        c.get("name")
        for c in inspector.get_unique_constraints("user_settings")
        if c.get("name")
    }
    if "uq_user_settings_tenant" in unique_names:
        op.drop_constraint("uq_user_settings_tenant", "user_settings", type_="unique")

    check_names = {
        c.get("name")
        for c in inspector.get_check_constraints("user_settings")
        if c.get("name")
    }
    if "ck_user_settings_singleton" not in check_names:
        op.create_check_constraint(
            "ck_user_settings_singleton",
            "user_settings",
            "id = 'singleton'",
        )
