"""Add scheduled workflow preview generation.

Revision ID: 0005_scheduled_workflow_previews
Revises: 0004_junk_scan_signals
"""

import sqlalchemy as sa
from alembic import op

revision: str = "0005_scheduled_workflow_previews"
down_revision: str | None = "0004_junk_scan_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    scan_columns = {column["name"] for column in inspector.get_columns("scan_jobs")}
    schedule_columns = {column["name"] for column in inspector.get_columns("schedules")}
    if "post_workflow_id" not in scan_columns:
        with op.batch_alter_table("scan_jobs") as batch:
            batch.add_column(sa.Column("post_workflow_id", sa.String(length=36), nullable=True))
            batch.create_foreign_key(
                "fk_scan_jobs_post_workflow_id",
                "workflows",
                ["post_workflow_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if "workflow_id" not in schedule_columns or "generate_preview" not in schedule_columns:
        with op.batch_alter_table("schedules") as batch:
            if "workflow_id" not in schedule_columns:
                batch.add_column(sa.Column("workflow_id", sa.String(length=36), nullable=True))
                batch.create_foreign_key(
                    "fk_schedules_workflow_id",
                    "workflows",
                    ["workflow_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if "generate_preview" not in schedule_columns:
                batch.add_column(
                    sa.Column(
                        "generate_preview",
                        sa.Boolean(),
                        nullable=False,
                        server_default=sa.false(),
                    )
                )


def downgrade() -> None:
    with op.batch_alter_table("schedules") as batch:
        batch.drop_constraint("fk_schedules_workflow_id", type_="foreignkey")
        batch.drop_column("generate_preview")
        batch.drop_column("workflow_id")
    with op.batch_alter_table("scan_jobs") as batch:
        batch.drop_constraint("fk_scan_jobs_post_workflow_id", type_="foreignkey")
        batch.drop_column("post_workflow_id")
