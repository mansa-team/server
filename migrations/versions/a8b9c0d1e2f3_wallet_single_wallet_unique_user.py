"""wallet single-wallet: merge multi-wallets, UNIQUE(userId)

Revision ID: a8b9c0d1e2f3
Revises: f2a3b4c5d6e7

Single-wallet enforcement for the IDOR fix: the wallet id is now resolved
server-side from the authenticated user, so one user must own at most one
wallet. Upgrade merges any multi-wallet users via chronological ledger replay
into the surviving (lowest walletId) wallet, then adds UNIQUE(userId).

Fail-loud cases (raise, never silently discard user data):
- orphan child rows pointing at a nonexistent wallet;
- earnings-accrual collisions across a user's wallets (same
  ticker/exDate/kind in two wallets): operator merges those rows by hand,
  then re-runs the migration.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CHILD_TABLES = ("transactions", "holdings", "targets", "snapshots", "earnings")


def _multis(connection) -> list:
    return connection.execute(
        sa.text("SELECT userId, COUNT(*) AS n FROM wallets GROUP BY userId HAVING COUNT(*) > 1")
    ).all()


def _orphans(connection) -> list:
    found = []
    for table in _CHILD_TABLES:
        rows = connection.execute(
            sa.text(
                f"SELECT c.* FROM {table} c "  # noqa: S608 - table is a fixed allowlist above
                "LEFT JOIN wallets w ON w.walletId = c.walletId "
                "WHERE w.walletId IS NULL LIMIT 10"
            )
        ).all()
        if rows:
            found.append((table, rows))
    return found


def _merge_user(connection, userId: int) -> None:
    walletIds = [
        row[0]
        for row in connection.execute(
            sa.text("SELECT walletId FROM wallets WHERE userId = :user ORDER BY walletId"),
            {"user": userId},
        ).all()
    ]
    survivor, losers = walletIds[0], walletIds[1:]
    loserList = ", ".join(str(walletId) for walletId in losers)

    collisions = connection.execute(
        sa.text(
            "SELECT ticker, exDate, kind, COUNT(*) AS n FROM earnings "
            f"WHERE walletId IN ({survivor}, {loserList}) "  # noqa: S608 - ids are ints from our own SELECT
            "GROUP BY ticker, exDate, kind HAVING COUNT(*) > 1"
        )
    ).all()
    if collisions:
        raise RuntimeError(
            f"wallet merge blocked for userId={userId}: earnings-accrual collisions {collisions}. "
            "Merge those accrual rows by hand, then re-run the migration."
        )
    targetCollisions = connection.execute(
        sa.text(
            "SELECT keyKind, keyValue, COUNT(*) AS n FROM targets "
            f"WHERE walletId IN ({survivor}, {loserList}) "  # noqa: S608 - ids are ints from our own SELECT
            "GROUP BY keyKind, keyValue HAVING COUNT(*) > 1"
        )
    ).all()
    if targetCollisions:
        raise RuntimeError(
            f"wallet merge blocked for userId={userId}: rebalance-target collisions {targetCollisions}. "
            "Pick the winning percentages by hand, then re-run the migration."
        )

    connection.execute(
        sa.text(f"UPDATE transactions SET walletId = :keep WHERE walletId IN ({loserList})"),  # noqa: S608
        {"keep": survivor},
    )
    connection.execute(
        sa.text(f"UPDATE earnings SET walletId = :keep WHERE walletId IN ({loserList})"),  # noqa: S608
        {"keep": survivor},
    )
    connection.execute(
        sa.text(f"UPDATE targets SET walletId = :keep WHERE walletId IN ({loserList})"),  # noqa: S608
        {"keep": survivor},
    )
    # Holdings/snapshots are derived caches: drop and rebuild the survivor's
    # holdings from the merged ledger below.
    for table in ("holdings", "snapshots"):
        connection.execute(sa.text(f"DELETE FROM {table} WHERE walletId IN ({survivor}, {loserList})"))  # noqa: S608

    entries = connection.execute(
        sa.text(
            "SELECT ticker, assetType, side, quantity, price, costs FROM transactions "
            "WHERE walletId = :keep ORDER BY date, entryId"
        ),
        {"keep": survivor},
    ).all()
    position: dict = {}
    for ticker, assetType, side, quantity, price, costs in entries:
        quantity, price, costs = float(quantity), float(price), float(costs)
        state = position.setdefault(ticker, {"asset": assetType, "quantity": 0.0, "avg": 0.0})
        if side == "Compra":
            total = state["quantity"] * state["avg"] + quantity * price + costs
            state["quantity"] += quantity
            state["avg"] = total / state["quantity"]
        else:
            state["quantity"] -= quantity
    # Ratings rebuild as NULL; positions refresh them from XANGO on next read.
    for ticker, state in position.items():
        if state["quantity"] <= 0:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO holdings (walletId, assetType, ticker, quantity, avgPrice, rating) "
                "VALUES (:wallet, :asset, :ticker, :quantity, :avg, NULL)"
            ),
            {
                "wallet": survivor,
                "asset": state["asset"],
                "ticker": ticker,
                "quantity": state["quantity"],
                "avg": state["avg"],
            },
        )
    connection.execute(sa.text(f"DELETE FROM wallets WHERE walletId IN ({loserList})"))  # noqa: S608


def upgrade() -> None:
    """Upgrade schema."""
    connection = op.get_bind()
    orphans = _orphans(connection)
    if orphans:
        detail = {table: len(rows) for table, rows in orphans}
        raise RuntimeError(
            f"wallet merge blocked: orphan child rows with no wallet {detail}. "
            "Reassign or delete them by hand, then re-run the migration."
        )
    for userId, _ in _multis(connection):
        _merge_user(connection, int(userId))
    op.create_unique_constraint("uq_wallets_user", "wallets", ["userId"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_wallets_user", "wallets", type_="unique")
