import logging
from datetime import date as dateType

from sqlalchemy.orm import Session

from main.app.stocks_api.sync_cache import cache as walletCache
from main.app.wallet.earnings import EarningsManager
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning, Transaction

logger = logging.getLogger(__name__)

PROGRESSION_EPOCH = "1970-01-01T00:00:00"
MAX_POINTS = 2000


def buyFlow(quantity: float, price: float, costs: float) -> float:
    return quantity * price + costs


def sellFlow(quantity: float, price: float, costs: float) -> float:
    return quantity * price - costs


class AnalyticsManager:
    # Canonical daily progression: every trading day in [from, to] with equity +
    # invested. Bucketing (weekly/monthly) + granularity resolution are
    # client-side. Only the MAX_POINTS stride cap stays server as payload guard.
    @classmethod
    @walletCache(
        ttl="6h",
        key="wallet:progression:{walletId}:{fromIso}:{toIso}:{recalcKey}:{entriesSnap}",
    )
    def cachedProgression(
        cls,
        walletId: int,
        fromIso: str,
        toIso: str,
        recalcKey: str,
        entriesSnap: tuple[tuple[str, str, str, float, float, float, int], ...],
    ) -> dict:
        del recalcKey

        tickers = sorted({entryTicker for entryTicker, _, _, _, _, _, _ in entriesSnap})
        closesByTicker: dict[str, list] = {}
        for ticker in tickers:
            closesByTicker[ticker] = PositionsManager.fetchPadraoCloses(ticker)

        sampleDays = sorted(
            {
                closeDay.isoformat()
                for series in closesByTicker.values()
                for closeDay, _ in series
                if fromIso <= closeDay.isoformat() <= toIso
            }
        )
        if not sampleDays:
            return {"granularity": "daily", "from": fromIso, "to": toIso, "points": []}

        if len(sampleDays) > MAX_POINTS:
            stride = -(-len(sampleDays) // MAX_POINTS)
            lastDay = sampleDays[-1]
            sampleDays = sampleDays[::stride]
            if sampleDays[-1] != lastDay:
                sampleDays.append(lastDay)

        entriesByTicker: dict[str, list] = {}
        for entryTicker, entryIso, entrySide, entryQty, entryPrice, entryCosts, entryId in entriesSnap:
            entriesByTicker.setdefault(entryTicker, []).append(
                (entryIso, entrySide, entryQty, entryPrice, entryCosts, entryId)
            )
        for tickerRows in entriesByTicker.values():
            tickerRows.sort()

        firstEntryIso = min(entryIso for _, entryIso, _, _, _, _, _ in entriesSnap)

        state: dict[str, dict] = {
            ticker: {"qty": 0.0, "invested": 0.0, "entryIdx": 0, "closeIdx": 0, "lastClose": None} for ticker in tickers
        }
        points = []
        for dayIso in sampleDays:
            if dayIso < firstEntryIso:
                continue
            equity = 0.0
            invested = 0.0
            for ticker in tickers:
                tickerState = state[ticker]
                # Advance ledger pointer through entries on/before this sample day.
                rows = entriesByTicker.get(ticker, [])
                while tickerState["entryIdx"] < len(rows) and rows[tickerState["entryIdx"]][0] <= dayIso:
                    _, entrySide, entryQty, entryPrice, entryCosts, _ = rows[tickerState["entryIdx"]]
                    if entrySide == "Compra":
                        tickerState["qty"] += entryQty
                        tickerState["invested"] += buyFlow(entryQty, entryPrice, entryCosts)
                    else:
                        tickerState["qty"] -= entryQty
                        tickerState["invested"] -= sellFlow(entryQty, entryPrice, entryCosts)
                    tickerState["entryIdx"] += 1
                # Forward-fill close: last known close on/before this sample day.
                series = closesByTicker[ticker]
                while (
                    tickerState["closeIdx"] < len(series) and series[tickerState["closeIdx"]][0].isoformat() <= dayIso
                ):
                    tickerState["lastClose"] = series[tickerState["closeIdx"]][1]
                    tickerState["closeIdx"] += 1
                if tickerState["lastClose"] is not None:
                    equity += tickerState["qty"] * tickerState["lastClose"]
                invested += tickerState["invested"]
            points.append({"date": dayIso, "equity": equity, "invested": invested})
        return {"granularity": "daily", "from": fromIso, "to": toIso, "points": points}

    @classmethod
    def getProgression(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> dict:
        from main.app.wallet.wallets import WalletsManager

        wallet = WalletsManager.getWallet(db, walletId, userId)
        recalcStamp = wallet.lastRecalc
        recalcKey = str(recalcStamp) if recalcStamp is not None else PROGRESSION_EPOCH
        ledgerRows = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId)
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        if not ledgerRows:
            return {"granularity": "daily", "from": start.isoformat(), "to": end.isoformat(), "points": []}
        entriesSnap = tuple(
            (
                str(ledgerRow.ticker),
                str(ledgerRow.date),
                str(ledgerRow.side),
                float(ledgerRow.quantity),
                float(ledgerRow.price),
                float(ledgerRow.costs),
                int(ledgerRow.entryId),
            )
            for ledgerRow in ledgerRows
        )
        return cls.cachedProgression(walletId, start.isoformat(), end.isoformat(), recalcKey, entriesSnap)

    @classmethod
    def getCashflows(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> dict:
        # Canonical raw: windowed ledger rows. Month buckets + rounding + totals are client-side.
        from main.app.wallet.wallets import WalletsManager

        WalletsManager.getWallet(db, walletId, userId)
        ledgerRows = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId, Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        rows = []
        for ledgerRow in ledgerRows:
            quantity, price, costs = float(ledgerRow.quantity), float(ledgerRow.price), float(ledgerRow.costs)
            if ledgerRow.side == "Compra":
                flowIn, flowOut = buyFlow(quantity, price, costs), 0.0
            else:
                flowIn, flowOut = 0.0, sellFlow(quantity, price, costs)
            rows.append(
                {
                    "date": str(ledgerRow.date),
                    "side": str(ledgerRow.side),
                    "ticker": str(ledgerRow.ticker),
                    "quantity": quantity,
                    "price": price,
                    "costs": costs,
                    "in": flowIn,
                    "out": flowOut,
                }
            )
        return {"from": start.isoformat(), "to": end.isoformat(), "rows": rows}

    @classmethod
    def getDividendsMonthly(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> dict:
        # Canonical raw: windowed earning rows. Month buckets + rounding + totals are client-side.
        from main.app.wallet.wallets import WalletsManager

        WalletsManager.getWallet(db, walletId, userId)
        EarningsManager.maybeAutoSync(db, walletId, userId)
        earningRows = (
            db.query(Earning)
            .filter(Earning.walletId == walletId, Earning.payDate >= start, Earning.payDate <= end)
            .order_by(Earning.payDate, Earning.earningId)
            .all()
        )
        rows = [
            {
                "pay_date": str(earningRow.payDate),
                "ticker": str(earningRow.ticker),
                "kind": str(earningRow.kind),
                "gross": float(earningRow.gross),
                "net": float(earningRow.netIrAdjusted),
            }
            for earningRow in earningRows
        ]
        return {"from": start.isoformat(), "to": end.isoformat(), "rows": rows}
