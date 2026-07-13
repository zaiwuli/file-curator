"""Add opt-in content hashing to scan jobs.

Revision ID: 0003_scan_content_hash
Revises: 0002_review_decisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_scan_content_hash"
down_revision: str | None = "0002_review_decisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("scan_jobs")}
    if "hash_contents" not in columns:
        op.add_column(
            "scan_jobs",
            sa.Column("hash_contents", sa.Boolean(), nullable=False, server_default=sa.false()),
        )


def downgrade() -> None:
    op.drop_column("scan_jobs", "hash_contents")
