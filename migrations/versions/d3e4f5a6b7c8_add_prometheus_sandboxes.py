"""add prometheus_sandboxes table

Revision ID: d3e4f5a6b7c8
Revises: c2e4f6a8b0c1
Create Date: 2026-07-17 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: Union[str, None] = "c2e4f6a8b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prometheus_sandboxes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("sandboxId", sa.String(length=255), nullable=False),
        sa.Column("workspacePath", sa.String(length=500), nullable=False),
        sa.Column("lastActivity", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.Column("createdAt", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_prometheus_sandboxes_userId", "prometheus_sandboxes", ["userId"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_prometheus_sandboxes_userId", table_name="prometheus_sandboxes")
    op.drop_table("prometheus_sandboxes")
