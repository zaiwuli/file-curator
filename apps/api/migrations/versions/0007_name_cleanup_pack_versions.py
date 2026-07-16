"""Add versioned name cleanup rule packs.

Revision ID: 0007_name_cleanup_pack_versions
Revises: 0006_junk_rule_pack_versions
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0007_name_cleanup_pack_versions"
down_revision: str | None = "0006_junk_rule_pack_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "name_cleanup_packs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "name_cleanup_pack_versions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("pack_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("change_note", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["pack_id"], ["name_cleanup_packs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pack_id", "version"),
    )
    op.create_index(
        "ix_name_cleanup_pack_versions_pack_id",
        "name_cleanup_pack_versions",
        ["pack_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_name_cleanup_pack_versions_pack_id",
        table_name="name_cleanup_pack_versions",
    )
    op.drop_table("name_cleanup_pack_versions")
    op.drop_table("name_cleanup_packs")
