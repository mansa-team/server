"""holding rating numeric

Revision ID: e2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-10-14 00:00:00.000000

Holding.rating was SmallInteger; Xango scores are decimal 0-100 and MySQL
SMALLINT rounded them. Widen to Numeric(5, 2).
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "holdings",
        "rating",
        existing_type=sa.SmallInteger(),
        type_=sa.Numeric(precision=5, scale=2),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "holdings",
        "rating",
        existing_type=sa.Numeric(precision=5, scale=2),
        type_=sa.SmallInteger(),
        existing_nullable=True,
    )
