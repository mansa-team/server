"""drop workspacePath column from prometheus_sandboxes

Revision ID: e5f6a7b8c9d0
Revises: d3e4f5a6b7c8
Create Date: 2026-08-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d3df3fc5ca72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("prometheus_sandboxes", "workspacePath")


def downgrade() -> None:
    op.add_column(
        "prometheus_sandboxes",
        sa.Column("workspacePath", sa.String(length=500), nullable=True),
    )
