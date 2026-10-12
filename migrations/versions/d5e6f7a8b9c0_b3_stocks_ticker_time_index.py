"""composite sort index for b3 stocks feather rebuild

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-10-11 00:00:00.000000

Backs the ORDER BY in main/app/stocks_api/build.py buildFeatherCache,
whose filesort filled /var/tmp on the stocks host
(pymysql errno 28, Can't create/write to file '/var/tmp/...').

b3_stocks lives in the STOCKS database (separate host), NOT the user
database alembic manages via migrations/env.py, so upgrade/downgrade
connect with config.stocksEngine directly instead of op.

TICKER/TIME are TEXT, so a plain composite index would be a prefix
index, which MySQL cannot use for ORDER BY (EXPLAIN kept Using
filesort). The functional index below serves the query's CAST ORDER BY
via index-order scan (verified: EXPLAIN shows key use, no filesort).
"""

from typing import Sequence, Union

from sqlalchemy import text

# revision identifiers, used by Alembic.
revision: str = "d5e6f7a8b9c0"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "ix_b3_stocks_ticker_time"
CREATE_SQL = f"CREATE INDEX {INDEX_NAME} ON b3_stocks ((CAST(TICKER AS CHAR(10))) ASC, (CAST(TIME AS DATETIME)) DESC)"


def upgrade() -> None:
    from config import stocksEngine

    with stocksEngine.connect() as conn:
        exists = conn.execute(text("SHOW INDEX FROM b3_stocks")).fetchall()
        if not any(row[2] == INDEX_NAME for row in exists):
            conn.execute(text(CREATE_SQL))
            conn.commit()


def downgrade() -> None:
    from config import stocksEngine

    with stocksEngine.connect() as conn:
        exists = conn.execute(text("SHOW INDEX FROM b3_stocks")).fetchall()
        if any(row[2] == INDEX_NAME for row in exists):
            conn.execute(text(f"DROP INDEX {INDEX_NAME} ON b3_stocks"))
            conn.commit()
