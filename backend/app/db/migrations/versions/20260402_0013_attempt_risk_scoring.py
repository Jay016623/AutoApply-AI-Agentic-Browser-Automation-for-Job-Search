"""Add risk and confidence fields to application attempts.

Revision ID: 20260402_0013
Revises: 20260402_0012
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260402_0013"
down_revision: str | None = "20260402_0012"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("application_attempts", sa.Column("risk_score", sa.Float(), nullable=False, server_default="0"))
    op.add_column("application_attempts", sa.Column("confidence_score", sa.Float(), nullable=False, server_default="1"))
    op.add_column("application_attempts", sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="low_risk"))


def downgrade() -> None:
    op.drop_column("application_attempts", "risk_level")
    op.drop_column("application_attempts", "confidence_score")
    op.drop_column("application_attempts", "risk_score")
