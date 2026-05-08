"""Add accessTokenHash, operatingSystem, lastActivityAt to user_sessions

Revision ID: add_access_token_hash
Revises: 4a2f1c9e3b5d
Create Date: 2026-05-05 11:30:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


revision: str = "add_access_token_hash"
down_revision: Union[str, Sequence[str], None] = "4a2f1c9e3b5d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add accessTokenHash, operatingSystem, lastActivityAt, sessionId to user_sessions."""
    conn = op.get_bind()
    
    # Change sessionId to VARCHAR(64) if currently smaller
    result = conn.execute(text("SHOW COLUMNS FROM user_sessions WHERE Field = 'sessionId'"))
    col = result.fetchone()
    if col and "varchar" in str(col).lower():
        type_str = str(col).lower()
        if "64" not in type_str:
            op.execute(text("ALTER TABLE user_sessions MODIFY sessionId VARCHAR(64) NOT NULL"))
    
    # Add accessTokenHash if not exists
    result = conn.execute(text("SHOW COLUMNS FROM user_sessions LIKE 'accessTokenHash'"))
    if not result.fetchone():
        op.add_column("user_sessions", sa.Column("accessTokenHash", sa.String(length=64), nullable=True))
    
    # Add operatingSystem if not exists
    result = conn.execute(text("SHOW COLUMNS FROM user_sessions LIKE 'operatingSystem'"))
    if not result.fetchone():
        op.add_column("user_sessions", sa.Column("operatingSystem", sa.String(length=50), nullable=True))
    
    # Add lastActivityAt if not exists
    result = conn.execute(text("SHOW COLUMNS FROM user_sessions LIKE 'lastActivityAt'"))
    if not result.fetchone():
        op.add_column("user_sessions", sa.Column("lastActivityAt", sa.TIMESTAMP(), nullable=True))
        op.execute(text("UPDATE user_sessions SET lastActivityAt = lastActiveAt WHERE lastActivityAt IS NULL AND lastActiveAt IS NOT NULL"))


def downgrade() -> None:
    """Remove columns from user_sessions."""
    op.drop_column("user_sessions", "lastActivityAt")
    op.drop_column("user_sessions", "operatingSystem")
    op.drop_column("user_sessions", "accessTokenHash")