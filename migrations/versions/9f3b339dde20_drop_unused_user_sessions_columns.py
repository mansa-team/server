"""drop unused user sessions columns

Revision ID: 9f3b339dde20
Revises: add_access_token_hash
Create Date: 2026-06-22 12:16:25.994796

Drops 7 orphan columns (and one index) on user_sessions that were added by
4a2f1c9e3b5d but are never populated by main/app/authentication/session.py.
The 11 columns the service actually uses remain: sessionId, userId,
accessTokenHash, deviceType, browser, operatingSystem, userAgent, isActive,
createdAt, lastActivityAt, expiresAt.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9f3b339dde20"
down_revision: Union[str, Sequence[str], None] = "add_access_token_hash"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ponytail: matches the column types declared in 4a2f1c9e3b5d so downgrade
# recreates the table to its pre-drop shape. NOT NULL string columns get a
# server_default of '' so downgrade works on populated tables.
_DROPPED_COLUMNS = [
    # (name, type, nullable, server_default)
    ("deviceFingerprint", sa.String(length=64), False, ""),
    ("deviceName", sa.String(length=255), True, None),
    ("browserVersion", sa.String(length=50), True, None),
    ("osVersion", sa.String(length=50), True, None),
    ("ipAddress", sa.String(length=45), False, ""),
    ("os", sa.String(length=50), True, None),
    ("lastActiveAt", sa.TIMESTAMP(), True, "CURRENT_TIMESTAMP"),
]
_DEVICE_FINGERPRINT_INDEX = "ix_user_sessions_deviceFingerprint"


def upgrade() -> None:
    """Drop 7 unused columns and their deviceFingerprint index."""
    op.drop_index(_DEVICE_FINGERPRINT_INDEX, table_name="user_sessions")
    for col_name, _col_type, _nullable, _default in _DROPPED_COLUMNS:
        op.drop_column("user_sessions", col_name)


def downgrade() -> None:
    """Recreate the 7 columns and the deviceFingerprint index."""
    for col_name, col_type, nullable, server_default in _DROPPED_COLUMNS:
        op.add_column(
            "user_sessions",
            sa.Column(
                col_name,
                col_type,
                nullable=nullable,
                server_default=sa.text(server_default) if server_default else None,
            ),
        )
    op.create_index(_DEVICE_FINGERPRINT_INDEX, "user_sessions", ["deviceFingerprint"])
