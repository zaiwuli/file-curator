"""Create the initial File Curator schema.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

from alembic import op

from file_curator.db import (
    AuditLog,
    ExecutionBatch,
    FileEntry,
    FileGroup,
    Operation,
    PipelineRun,
    Plan,
    ScanJob,
    Schedule,
    Source,
    StageResult,
    Workflow,
    WorkflowRevision,
)

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INITIAL_TABLES = [
    Source.__table__,
    ScanJob.__table__,
    FileEntry.__table__,
    FileGroup.__table__,
    Workflow.__table__,
    WorkflowRevision.__table__,
    PipelineRun.__table__,
    StageResult.__table__,
    Plan.__table__,
    Operation.__table__,
    ExecutionBatch.__table__,
    Schedule.__table__,
    AuditLog.__table__,
]


def upgrade() -> None:
    bind = op.get_bind()
    for table in INITIAL_TABLES:
        table.create(bind=bind, checkfirst=False)


def downgrade() -> None:
    bind = op.get_bind()
    for table in reversed(INITIAL_TABLES):
        table.drop(bind=bind, checkfirst=False)
