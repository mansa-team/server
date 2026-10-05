"""user_sessions sessionId int -> varchar(64) pk

Revision ID: f2a3b4c5d6e7
Revises: d4e5f6a7b8c9

Live DBs created by 4a2f1c9e3b5d carry sessionId INT PK AUTO_INCREMENT while
the model (main/models/user_session.py) and SessionManager.createSession
(main/app/authentication/session.py) use token_urlsafe(32) strings.
add_access_token_hash only converts when the column is already varchar, so
the int->varchar conversion never happened and string inserts 500
(pymysql 1366 Incorrect integer value).
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Convert sessionId INT AUTO_INCREMENT PK to VARCHAR(64) PK."""
    conn = op.get_bind()
    row = conn.execute(text("SHOW COLUMNS FROM user_sessions WHERE Field = 'sessionId'")).fetchone()
    if row is None:
        return
    mapping = row._mapping
    type_str = str(mapping["Type"]).lower()
    if "varchar(64)" in type_str:
        if mapping["Key"] != "PRI":
            op.execute(text("ALTER TABLE user_sessions ADD PRIMARY KEY (sessionId)"))
        return
    # Drop AUTO_INCREMENT first: MySQL refuses DROP PRIMARY KEY on one.
    op.execute(text("ALTER TABLE user_sessions MODIFY sessionId INT NOT NULL"))
    op.execute(text("ALTER TABLE user_sessions DROP PRIMARY KEY"))
    op.execute(text("ALTER TABLE user_sessions MODIFY sessionId VARCHAR(64) NOT NULL"))
    op.execute(text("ALTER TABLE user_sessions ADD PRIMARY KEY (sessionId)"))


def downgrade() -> None:
    """Revert sessionId to INT AUTO_INCREMENT PK.

    LOSSY: any token-string rows are truncated/destroyed by the
    VARCHAR->INT cast. Acceptable: the int PK could never hold a live
    token session, so rows present are pre-fix leftovers at worst.
    """
    op.execute(text("ALTER TABLE user_sessions DROP PRIMARY KEY"))
    op.execute(text("ALTER TABLE user_sessions MODIFY sessionId INT NOT NULL"))
    op.execute(text("ALTER TABLE user_sessions ADD PRIMARY KEY (sessionId)"))
    op.execute(text("ALTER TABLE user_sessions MODIFY sessionId INT NOT NULL AUTO_INCREMENT"))
