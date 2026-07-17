"""create prometheus_memories with baseScore

Revision ID: b1c2d3e4f5a6
Revises: add_access_token_hash
Create Date: 2026-07-13 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "9f3b339dde20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prometheus_memories",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("memoryKey", sa.String(length=100), nullable=False),
        sa.Column("memoryValue", sa.Text(), nullable=False),
        sa.Column("memoryType", sa.String(length=20), server_default="context", nullable=True),
        sa.Column("source", sa.String(length=20), server_default="inferred", nullable=True),
        sa.Column("baseScore", sa.Float(), server_default="1.0", nullable=True),
        sa.Column("accessCount", sa.Integer(), server_default="0", nullable=True),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("embeddingModel", sa.String(length=50), server_default="all-MiniLM-L6-v2", nullable=True),
        sa.Column("embeddingVersion", sa.String(length=20), server_default="1", nullable=True),
        sa.Column("contentHash", sa.String(length=32), nullable=True),
        sa.Column("createdAt", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("updatedAt", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("lastAccessedAt", sa.TIMESTAMP(), nullable=True),
        sa.Column("archivedAt", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("userId", "memoryKey", name="uk_prometheus_memories"),
    )
    op.create_index("idx_user_id", "prometheus_memories", ["userId"])
    op.create_index("idx_base_score", "prometheus_memories", ["userId", "baseScore"])
    op.create_index("idx_type", "prometheus_memories", ["userId", "memoryType"])
    op.execute("ALTER TABLE prometheus_memories ADD FULLTEXT INDEX ft_memory (memoryKey, memoryValue)")


def downgrade() -> None:
    op.drop_index("ft_memory", table_name="prometheus_memories")
    op.drop_index("idx_type", table_name="prometheus_memories")
    op.drop_index("idx_base_score", table_name="prometheus_memories")
    op.drop_index("idx_user_id", table_name="prometheus_memories")
    op.drop_table("prometheus_memories")


# ponytail: migration ran partially (table created, FULLTEXT index failed).
# Drop the table so alembic can re-run cleanly.
def fix_partial() -> None:
    op.execute("DROP TABLE IF EXISTS prometheus_memories")
