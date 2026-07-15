"""drop embeddingModel and embeddingVersion columns

Revision ID: c2e4f6a8b0c1
Revises: b1c2d3e4f5a6
Create Date: 2026-07-15 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c2e4f6a8b0c1"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("prometheus_memories", "embeddingModel")
    op.drop_column("prometheus_memories", "embeddingVersion")


def downgrade() -> None:
    op.add_column(
        "prometheus_memories",
        sa.Column("embeddingModel", sa.String(length=50), server_default="all-MiniLM-L6-v2", nullable=True),
    )
    op.add_column(
        "prometheus_memories", sa.Column("embeddingVersion", sa.String(length=20), server_default="1", nullable=True)
    )
