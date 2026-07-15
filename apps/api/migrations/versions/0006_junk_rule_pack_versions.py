"""Add versioned personal junk rule packs.

Revision ID: 0006_junk_rule_pack_versions
Revises: 0005_scheduled_workflow_previews
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0006_junk_rule_pack_versions"
down_revision: str | None = "0005_scheduled_workflow_previews"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "junk_rule_packs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "junk_rule_pack_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pack_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["junk_rule_packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pack_id", "version"),
    )
    op.create_index(
        "ix_junk_rule_pack_versions_pack_id", "junk_rule_pack_versions", ["pack_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_junk_rule_pack_versions_pack_id", table_name="junk_rule_pack_versions")
    op.drop_table("junk_rule_pack_versions")
    op.drop_table("junk_rule_packs")
