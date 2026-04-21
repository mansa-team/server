"""User sessions table

Revision ID: 4a2f1c9e3b5d
Revises: 25af7ad931e7
Create Date: 2026-04-20 10:00:00.000000

"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = "4a2f1c9e3b5d"
down_revision: Union[str, Sequence[str], None] = "25af7ad931e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "user_sessions",
        sa.Column("sessionId", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("userId", sa.Integer(), nullable=False),
        sa.Column("deviceFingerprint", sa.String(length=64), nullable=False),
        sa.Column("deviceName", sa.String(length=255), nullable=True),
        sa.Column("browser", sa.String(length=50), nullable=True),
        sa.Column("browserVersion", sa.String(length=50), nullable=True),
        sa.Column("os", sa.String(length=50), nullable=True),
        sa.Column("osVersion", sa.String(length=50), nullable=True),
        sa.Column("deviceType", sa.String(length=50), nullable=True),
        sa.Column("ipAddress", sa.String(length=45), nullable=False),
        sa.Column("userAgent", sa.Text(), nullable=True),
        sa.Column("isActive", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("lastActiveAt", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("createdAt", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("expiresAt", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["userId"], ["users.userId"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("sessionId"),
    )
    op.create_index(op.f("ix_user_sessions_userId"), "user_sessions", ["userId"])
    op.create_index(op.f("ix_user_sessions_deviceFingerprint"), "user_sessions", ["deviceFingerprint"])
    op.create_index(op.f("ix_user_sessions_isActive"), "user_sessions", ["isActive"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_user_sessions_isActive"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_deviceFingerprint"), table_name="user_sessions")
    op.drop_index(op.f("ix_user_sessions_userId"), table_name="user_sessions")
    op.drop_table("user_sessions")
