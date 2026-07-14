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
    with op.batch_alter_table("scan_jobs") as batch:
        batch.add_column(sa.Column("inspect_small_text", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("file_entries") as batch:
        batch.add_column(sa.Column("text_signals", sa.JSON(), nullable=False, server_default="[]"))


def downgrade() -> None:
    with op.batch_alter_table("file_entries") as batch:
        batch.drop_column("text_signals")
    with op.batch_alter_table("scan_jobs") as batch:
        batch.drop_column("inspect_small_text")
