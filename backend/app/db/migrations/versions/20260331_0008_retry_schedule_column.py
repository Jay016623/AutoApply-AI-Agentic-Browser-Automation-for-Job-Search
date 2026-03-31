"""Add next_retry_at to application attempts.

Revision ID: 20260331_0008
Revises: 20260331_0007
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0008"
down_revision: str | None = "20260331_0007"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_attempts", sa.Column("next_retry_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("application_attempts", "next_retry_at")
