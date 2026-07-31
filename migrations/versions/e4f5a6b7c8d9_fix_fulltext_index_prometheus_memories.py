"""add missing FULLTEXT index on prometheus_memories

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-07-22 03:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The original migration (b1c2d3e4f5a6) ran partially — table created but FULLTEXT index failed.
    # Check if index already exists before adding (idempotent).
    # ponytail: PREPARE/EXECUTE fails through SQLAlchemy — just check in Python.
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM information_schema.statistics "
            "WHERE table_schema = DATABASE() "
            "AND table_name = 'prometheus_memories' "
            "AND index_name = 'ft_memory'"
        )
    ).scalar()
    if not exists:
        op.execute("ALTER TABLE prometheus_memories ADD FULLTEXT INDEX ft_memory (memoryKey, memoryValue)")


def downgrade() -> None:
    op.execute("ALTER TABLE prometheus_memories DROP INDEX ft_memory")
