"""rename prometheus tables to orunmila

Revision ID: f7a8b9c0d1e2
Revises: f1a2b3c4d5e6
Create Date: 2026-09-17 00:00:00.000000

Renames prometheus, prometheus_memories and prometheus_sandboxes
tables (plus their constraints/indexes) to the orunmila naming,
matching the code rename (main/app/prometheus -> main/app/orunmila).

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.rename_table("prometheus", "orunmila")
    op.rename_table("prometheus_memories", "orunmila_memories")
    op.rename_table("prometheus_sandboxes", "orunmila_sandboxes")
    op.drop_constraint("uk_prometheus_memories", "orunmila_memories", type_="unique")
    op.create_unique_constraint("uk_orunmila_memories", "orunmila_memories", ["userId", "memoryKey"])
    op.drop_index("idx_user_id", table_name="orunmila_memories")
    op.create_index("idx_orunmila_user_id", "orunmila_memories", ["userId"])
    op.drop_index("idx_base_score", table_name="orunmila_memories")
    op.create_index("idx_orunmila_base_score", "orunmila_memories", ["userId", "score"])
    op.drop_index("idx_type", table_name="orunmila_memories")
    op.create_index("idx_orunmila_type", "orunmila_memories", ["userId", "memoryType"])
    op.execute("ALTER TABLE orunmila_memories DROP INDEX ft_memory")
    op.execute("ALTER TABLE orunmila_memories ADD FULLTEXT INDEX ft_orunmila_memory (memoryKey, memoryValue)")
    op.drop_index("ix_prometheus_sandboxes_userId", table_name="orunmila_sandboxes")
    op.create_index("ix_orunmila_sandboxes_userId", "orunmila_sandboxes", ["userId"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_orunmila_sandboxes_userId", table_name="orunmila_sandboxes")
    op.create_index("ix_prometheus_sandboxes_userId", "orunmila_sandboxes", ["userId"], unique=True)
    op.execute("ALTER TABLE orunmila_memories DROP INDEX ft_orunmila_memory")
    op.execute("ALTER TABLE orunmila_memories ADD FULLTEXT INDEX ft_memory (memoryKey, memoryValue)")
    op.drop_index("idx_orunmila_type", table_name="orunmila_memories")
    op.create_index("idx_type", "orunmila_memories", ["userId", "memoryType"])
    op.drop_index("idx_orunmila_base_score", table_name="orunmila_memories")
    op.create_index("idx_base_score", "orunmila_memories", ["userId", "score"])
    op.drop_index("idx_orunmila_user_id", table_name="orunmila_memories")
    op.create_index("idx_user_id", "orunmila_memories", ["userId"])
    op.drop_constraint("uk_orunmila_memories", "orunmila_memories", type_="unique")
    op.create_unique_constraint("uk_prometheus_memories", "orunmila_memories", ["userId", "memoryKey"])
    op.rename_table("orunmila_sandboxes", "prometheus_sandboxes")
    op.rename_table("orunmila_memories", "prometheus_memories")
    op.rename_table("orunmila", "prometheus")
