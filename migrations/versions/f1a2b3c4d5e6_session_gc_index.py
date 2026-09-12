"""composite index for session GC sweep (M2)

Revision ID: f1a2b3c4d5e6
Revises: e5f6a7b8c9d0
Create Date: 2026-09-03 00:00:00.000000

Adds ix_user_sessions_active_lastactive on
user_sessions (isActive, lastActivityAt), backing the 12h
removeInactiveSessions sweep which now also purges
expired-but-still-active rows (isActive & expiresAt < now).

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_user_sessions_active_lastactive",
        "user_sessions",
        ["isActive", "lastActivityAt"],
    )


def downgrade() -> None:
    op.drop_index("ix_user_sessions_active_lastactive", table_name="user_sessions")
