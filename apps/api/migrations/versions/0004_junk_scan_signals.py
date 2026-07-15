"""Add opt-in small-text scan signals.

Revision ID: 0004_junk_scan_signals
Revises: 0003_scan_content_hash
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0004_junk_scan_signals"
down_revision: str | None = "0003_scan_content_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    scan_columns = {column["name"] for column in inspector.get_columns("scan_jobs")}
    entry_columns = {column["name"] for column in inspector.get_columns("file_entries")}
    if "inspect_small_text" not in scan_columns:
        op.add_column(
            "scan_jobs",
            sa.Column(
                "inspect_small_text", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    if "text_signals" not in entry_columns:
        op.add_column(
            "file_entries",
            sa.Column("text_signals", sa.JSON(), nullable=False, server_default="[]"),
        )


def downgrade() -> None:
    with op.batch_alter_table("file_entries") as batch:
        batch.drop_column("text_signals")
    with op.batch_alter_table("scan_jobs") as batch:
        batch.drop_column("inspect_small_text")
