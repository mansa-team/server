# rename memory baseScore to score
#
# Revision ID: d3df3fc5ca72
# Revises: e4f5a6b7c8d9
# Create Date: 2026-07-31 15:59:11.918297
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3df3fc5ca72'
down_revision = 'e4f5a6b7c8d9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("prometheus_memories", "baseScore", new_column_name="score", existing_type=sa.Float(), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("prometheus_memories", "score", new_column_name="baseScore", existing_type=sa.Float(), existing_nullable=True)
