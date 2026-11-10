"""single-table b3_stocks: drop old wide quarter columns, add JSON history

Revision ID: b7c8d9e0f1a2
Revises: e2a3b4c5d6e7
Create Date: 2026-11-05 00:00:00.000000

The user requires one table, b3_stocks, so quarterly history is a single
JSON column (`HISTORICO TRIMESTRAL`) instead of a wide column per quarter
and instead of the cancelled b3_quarterly long table. A new quarter then
costs no DDL at all.

Why the wide design had to go: b3_stocks carried 655 quarter columns in
the old glued form `METRIC 1T2015`, all 100% NULL, and the table was at
956 of InnoDB's 1,017-column cap with the inline row already past the
8,126-byte limit. A pre-flight `ADD COLUMN __rowprobe DOUBLE NULL` failed
BOTH ways: ALGORITHM=INSTANT with errno 4157 ("max possible row size
already crosses max permissible row size") and the default path with
errno 1118 ("Row size too large (> 8126)"). The 655 columns are dropped
here in INSTANT chunks; a JSON value lives off-page as a 20-byte pointer
on this ROW_FORMAT=DYNAMIC table, so it does not recreate that wall.

The column pattern matches both the old glued `METRIC 1T2015` and the
spaced `METRIC 1T 2015` form, so a scrape that writes either one is
cleaned up instead of being left in the schema.

The filename still says b3_quarterly for history only: that table is
dropped by this migration and must not be recreated.

b3_stocks lives in the STOCKS database (separate host), NOT the user
database alembic manages via migrations/env.py, so upgrade/downgrade
connect with config.stocksEngine directly instead of op.
"""

import logging
import re
import time
from typing import Sequence, Union

from sqlalchemy import Connection, text

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "e2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOGGER = logging.getLogger(__name__)

# Both the old glued `METRIC 1T2015` and the spaced `METRIC 1T 2015` form.
QUARTER_PATTERN = r"[1-4]T\s*[0-9]{4}$"
QUARTER_NAME = re.compile(r"^(?P<metric>.+) (?P<quarter>[1-4])T\s*(?P<year>\d{4})$")
CHUNK_SIZE = 100
HISTORY_COLUMN = "HISTORICO TRIMESTRAL"

QUARTER_COLUMNS_SQL = """
SELECT COLUMN_NAME
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'b3_stocks'
  AND COLUMN_NAME REGEXP :pattern
ORDER BY ORDINAL_POSITION
"""

COLUMN_TYPE_SQL = """
SELECT DATA_TYPE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'b3_stocks'
  AND COLUMN_NAME = :name
"""

COLUMN_COUNT_SQL = """
SELECT COUNT(*)
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'b3_stocks'
"""


def quoteColumn(name: str) -> str:
    return f"`{name.replace('`', '``')}`"


def quarterColumns(conn: Connection) -> list[str]:
    found = conn.execute(text(QUARTER_COLUMNS_SQL), {"pattern": QUARTER_PATTERN}).scalars()
    columns = list(found)
    unparsed = [name for name in columns if not QUARTER_NAME.match(name)]
    if unparsed:
        raise RuntimeError(f"quarter columns do not parse as 'METRIC 1TYYYY': {unparsed}")
    return columns


def columnCount(conn: Connection) -> int:
    return int(conn.execute(text(COLUMN_COUNT_SQL)).scalar_one())


def anyQuarterValue(conn: Connection, columns: list[str]) -> bool:
    """Short-circuiting existence check: is any source quarter cell non-NULL?"""
    predicate = " OR ".join(f"{quoteColumn(name)} IS NOT NULL" for name in columns)
    found = conn.execute(text(f"SELECT 1 FROM b3_stocks WHERE {predicate} LIMIT 1")).first()
    return found is not None


def quarterlyRows(conn: Connection) -> int:
    """Rows in the cancelled long table; 0 when the table is absent."""
    try:
        return int(conn.execute(text("SELECT COUNT(*) FROM b3_quarterly")).scalar_one())
    except Exception:  # noqa: BLE001 - a missing table is the normal case
        conn.rollback()
        return 0


def dropQuarterlyColumns(conn: Connection, columns: list[str]) -> None:
    for start in range(0, len(columns), CHUNK_SIZE):
        chunk = columns[start : start + CHUNK_SIZE]
        drops = ", ".join(f"DROP COLUMN {quoteColumn(name)}" for name in chunk)
        try:
            conn.execute(text(f"ALTER TABLE b3_stocks {drops}, ALGORITHM=INSTANT"))
            path = "INSTANT"
        except Exception:  # noqa: BLE001 - the fallback is the documented path
            conn.rollback()
            LOGGER.warning("INSTANT refused for chunk starting %s, retrying without it", chunk[0])
            conn.execute(text(f"ALTER TABLE b3_stocks {drops}"))
            path = "COPY/INPLACE"
        conn.commit()
        LOGGER.info("dropped %d columns via %s", len(chunk), path)


def ensureHistoryColumn(conn: Connection) -> bool:
    """Add the JSON column when absent; returns True when it was added."""
    dataType = conn.execute(text(COLUMN_TYPE_SQL), {"name": HISTORY_COLUMN}).scalar()
    if dataType is None:
        conn.execute(text(f"ALTER TABLE b3_stocks ADD COLUMN {quoteColumn(HISTORY_COLUMN)} JSON NULL"))
        conn.commit()
        return True
    if dataType != "json":
        raise RuntimeError(f"{HISTORY_COLUMN} exists with type {dataType}, expected json")
    return False


def upgrade() -> None:
    from config import stocksEngine

    started = time.perf_counter()
    with stocksEngine.connect() as conn:
        columns = quarterColumns(conn)
        if columns and anyQuarterValue(conn, columns):
            raise RuntimeError(
                f"{len(columns)} old quarter columns still hold non-NULL cells; "
                "refusing to drop them, no copy exists in this design"
            )
        if columns:
            dropQuarterlyColumns(conn, columns)
        else:
            LOGGER.info("no old quarter columns left")

        rows = quarterlyRows(conn)
        if rows:
            raise RuntimeError(f"b3_quarterly still holds {rows} rows; refusing to drop it")
        conn.execute(text("DROP TABLE IF EXISTS b3_quarterly"))
        conn.commit()
        LOGGER.info("b3_quarterly absent")

        added = ensureHistoryColumn(conn)
        dataType = conn.execute(text(COLUMN_TYPE_SQL), {"name": HISTORY_COLUMN}).scalar()
        if dataType != "json":
            raise RuntimeError(f"{HISTORY_COLUMN} is {dataType}, expected json")
        LOGGER.info(
            "b3_stocks %d columns, %s json (%s), %d quarter columns dropped, %.1fs",
            columnCount(conn),
            HISTORY_COLUMN,
            "added" if added else "already present",
            len(columns),
            time.perf_counter() - started,
        )


def downgrade() -> None:
    """No-op on purpose.

    Restoring the 655 wide quarter columns would re-trigger errno 1118
    (row size too large); the quarterly history, once scraped, lives in
    the `HISTORICO TRIMESTRAL` JSON column.
    """
