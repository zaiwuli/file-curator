"""Create the initial File Curator schema.

Revision ID: 0001_initial
Revises:
"""

from collections.abc import Sequence

from alembic import op

from file_curator.db import Base

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
