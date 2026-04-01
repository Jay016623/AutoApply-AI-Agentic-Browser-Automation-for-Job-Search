"""Add durable artifact storage metadata fields.

Revision ID: 20260401_0009
Revises: 20260331_0008
Create Date: 2026-04-01
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260401_0009"
down_revision: str | None = "20260331_0008"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("proof_artifacts", sa.Column("storage_backend", sa.String(length=32), nullable=True))
    op.add_column("proof_artifacts", sa.Column("object_key", sa.String(length=512), nullable=True))
    op.add_column("proof_artifacts", sa.Column("bucket_name", sa.String(length=255), nullable=True))
    op.add_column("proof_artifacts", sa.Column("content_type", sa.String(length=120), nullable=True))
    op.add_column("proof_artifacts", sa.Column("size_bytes", sa.Integer(), nullable=True))

    op.execute("UPDATE proof_artifacts SET storage_backend = 'local' WHERE storage_backend IS NULL")
    op.alter_column("proof_artifacts", "storage_backend", nullable=False)
    op.create_index("ix_proof_backend", "proof_artifacts", ["storage_backend"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_proof_backend", table_name="proof_artifacts")
    op.drop_column("proof_artifacts", "size_bytes")
    op.drop_column("proof_artifacts", "content_type")
    op.drop_column("proof_artifacts", "bucket_name")
    op.drop_column("proof_artifacts", "object_key")
    op.drop_column("proof_artifacts", "storage_backend")
