"""drop meaningless accessTokenHash from user_sessions

Revision ID: c3d4e5f6a7b8
Revises: a8b9c0d1e2f3

Reviewer issue #9: accessTokenHash was a sha256 of a random token whose
pre-image was never stored or returned, so nothing ever verified against it —
session lookup/revocation key on sessionId only. A security-looking field
that participates in no security invariant is removed.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column("user_sessions", "accessTokenHash")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column("user_sessions", sa.Column("accessTokenHash", sa.String(length=64), nullable=True))
