"""rename relevanceScore to baseScore

Revision ID: d4e5f6a7b8c9
Revises: b1c2d3e4f5a6
Create Date: 2026-07-14
"""

from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("prometheus_memories", "relevanceScore", new_column_name="baseScore")


def downgrade() -> None:
    op.alter_column("prometheus_memories", "baseScore", new_column_name="relevanceScore")
