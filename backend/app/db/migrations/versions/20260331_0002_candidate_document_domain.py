"""Candidate and document domain foundations.

Revision ID: 20260331_0002
Revises: 20260331_0001
Create Date: 2026-03-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260331_0002"
down_revision: str | None = "20260331_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidates",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("headline", sa.String(length=255), nullable=True),
        sa.Column("settings", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_candidate_tenant", "candidates", ["tenant_id"], unique=False)
    op.create_index("ix_candidate_active", "candidates", ["is_active"], unique=False)
    op.create_index("ix_candidate_tenant_email", "candidates", ["tenant_id", "email"], unique=True)

    op.create_table(
        "candidate_profile_snapshots",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False, server_default="manual"),
        sa.Column("summary", sa.String(length=4000), nullable=False, server_default=""),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("experience", sa.JSON(), nullable=False),
        sa.Column("education", sa.JSON(), nullable=False),
        sa.Column("certifications", sa.JSON(), nullable=False),
        sa.Column("snapshot_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_candidate_profile_version"),
    )
    op.create_index(
        "ix_candidate_profile_tenant",
        "candidate_profile_snapshots",
        ["tenant_id"],
        unique=False,
    )

    op.create_table(
        "resume_versions",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("resume_id", sa.String(length=32), nullable=True),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False, server_default="Resume"),
        sa.Column("template_id", sa.String(length=50), nullable=False, server_default="modern"),
        sa.Column("variant_type", sa.String(length=30), nullable=False, server_default="base"),
        sa.Column("file_path_pdf", sa.String(length=500), nullable=True),
        sa.Column("file_path_docx", sa.String(length=500), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_resume_version"),
    )
    op.create_index("ix_resume_version_tenant", "resume_versions", ["tenant_id"], unique=False)
    op.create_index("ix_resume_version_candidate", "resume_versions", ["candidate_id"], unique=False)

    op.create_table(
        "cover_letter_versions",
        sa.Column("tenant_id", sa.String(length=32), nullable=True),
        sa.Column("candidate_id", sa.String(length=32), nullable=False),
        sa.Column("job_id", sa.String(length=32), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False, server_default="Cover Letter"),
        sa.Column("template_id", sa.String(length=50), nullable=False, server_default="standard"),
        sa.Column("file_path_pdf", sa.String(length=500), nullable=True),
        sa.Column("file_path_docx", sa.String(length=500), nullable=True),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["candidate_id"], ["candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_id", "version", name="uq_cover_letter_version"),
    )
    op.create_index(
        "ix_cover_letter_version_tenant",
        "cover_letter_versions",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_cover_letter_version_candidate",
        "cover_letter_versions",
        ["candidate_id"],
        unique=False,
    )

    op.add_column("resumes", sa.Column("candidate_id", sa.String(length=32), nullable=True))
    op.create_foreign_key(
        "fk_resumes_candidate_id",
        "resumes",
        "candidates",
        ["candidate_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_resumes_candidate_id", "resumes", type_="foreignkey")
    op.drop_column("resumes", "candidate_id")

    op.drop_index("ix_cover_letter_version_candidate", table_name="cover_letter_versions")
    op.drop_index("ix_cover_letter_version_tenant", table_name="cover_letter_versions")
    op.drop_table("cover_letter_versions")

    op.drop_index("ix_resume_version_candidate", table_name="resume_versions")
    op.drop_index("ix_resume_version_tenant", table_name="resume_versions")
    op.drop_table("resume_versions")

    op.drop_index("ix_candidate_profile_tenant", table_name="candidate_profile_snapshots")
    op.drop_table("candidate_profile_snapshots")

    op.drop_index("ix_candidate_tenant_email", table_name="candidates")
    op.drop_index("ix_candidate_active", table_name="candidates")
    op.drop_index("ix_candidate_tenant", table_name="candidates")
    op.drop_table("candidates")
