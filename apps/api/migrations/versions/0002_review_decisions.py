"""Persist per-file review decisions.

Revision ID: 0002_review_decisions
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_review_decisions"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("file_entry_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("target_relative_path", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["file_entry_id"], ["file_entries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["pipeline_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "file_entry_id"),
    )
    op.create_index("ix_review_decisions_run_id", "review_decisions", ["run_id"])
    op.create_index(
        "ix_review_decisions_file_entry_id", "review_decisions", ["file_entry_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_review_decisions_file_entry_id", table_name="review_decisions")
    op.drop_index("ix_review_decisions_run_id", table_name="review_decisions")
    op.drop_table("review_decisions")
