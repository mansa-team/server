import logging
from datetime import date as dateType
from typing import Literal

from sqlalchemy.orm import Session

from main.app.stocks_api.sync_cache import cache as walletCache
from main.app.wallet.earnings import EarningsManager
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning, Transaction

logger = logging.getLogger(__name__)

Granularity = Literal["auto", "daily", "weekly", "monthly"]

PROGRESSION_EPOCH = "1970-01-01T00:00:00"
MAX_POINTS = 2000


def buyFlow(quantity: float, price: float, costs: float) -> float:
    return quantity * price + costs


def sellFlow(quantity: float, price: float, costs: float) -> float:
    return quantity * price - costs


def monthRange(start: dateType, end: dateType) -> list[str]:
    months = []
    cursor = dateType(start.year, start.month, 1)
    while cursor <= end:
        months.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = dateType(cursor.year + 1, 1, 1)
        else:
            cursor = dateType(cursor.year, cursor.month + 1, 1)
    return months


class AnalyticsManager:
    @classmethod
    def resolveGranularity(cls, granularity: str, start: dateType, end: dateType) -> str:
        if granularity != "auto":
            return granularity
        spanDays = (end - start).days
        if spanDays <= 93:
            return "daily"
        if spanDays <= 730:
            return "weekly"
        return "monthly"

    @classmethod
    @walletCache(
        ttl="6h",
        key="wallet:progression:{walletId}:{fromIso}:{toIso}:{granularity}:{recalcKey}:{entriesSnap}",
    )
    def cachedProgression(
        cls,
        walletId: int,
        fromIso: str,
        toIso: str,
        granularity: str,
        recalcKey: str,
        entriesSnap: tuple[tuple[str, str, str, float, float, float, int], ...],
    ) -> dict:
        del recalcKey

        tickers = sorted({entryTicker for entryTicker, _, _, _, _, _, _ in entriesSnap})
        closesByTicker: dict[str, list] = {}
        for ticker in tickers:
            closesByTicker[ticker] = PositionsManager.fetchPadraoCloses(ticker)

        tradingDays = sorted(
            {
                closeDay.isoformat()
                for series in closesByTicker.values()
                for closeDay, _ in series
                if fromIso <= closeDay.isoformat() <= toIso
            }
        )
        if not tradingDays:
            return {"granularity": granularity, "from": fromIso, "to": toIso, "points": []}

        def bucketKey(dayIso: str) -> str:
            if granularity == "daily":
                return dayIso
            day = dateType.fromisoformat(dayIso)
            if granularity == "weekly":
                isoYear, isoWeek, _ = day.isocalendar()
                return f"{isoYear}-W{isoWeek:02d}"
            return dayIso[:7]

        bucketDay: dict[str, str] = {}
        for dayIso in tradingDays:
            bucketDay[bucketKey(dayIso)] = dayIso
        sampleDays = sorted(bucketDay.values())
        if len(sampleDays) > MAX_POINTS:
            stride = -(-len(sampleDays) // MAX_POINTS)
            sampleDays = sampleDays[::stride]
            if sampleDays[-1] != bucketDay[sorted(bucketDay)[-1]]:
                sampleDays.append(sorted(bucketDay.values())[-1])

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
        return {"granularity": granularity, "from": fromIso, "to": toIso, "points": points}

    @classmethod
    def getProgression(
        cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType, granularity: str
    ) -> dict:
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
            resolved = cls.resolveGranularity(granularity, start, end)
            return {"granularity": resolved, "from": start.isoformat(), "to": end.isoformat(), "points": []}
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
        resolved = cls.resolveGranularity(granularity, start, end)
        return cls.cachedProgression(walletId, start.isoformat(), end.isoformat(), resolved, recalcKey, entriesSnap)

    @classmethod
    def getCashflows(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> dict:
        from main.app.wallet.wallets import WalletsManager

        WalletsManager.getWallet(db, walletId, userId)
        ledgerRows = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId, Transaction.date >= start, Transaction.date <= end)
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        buckets: dict[str, dict] = {month: {"in": 0.0, "out": 0.0} for month in monthRange(start, end)}
        for ledgerRow in ledgerRows:
            month = str(ledgerRow.date)[:7]
            quantity, price, costs = float(ledgerRow.quantity), float(ledgerRow.price), float(ledgerRow.costs)
            if ledgerRow.side == "Compra":
                buckets[month]["in"] += buyFlow(quantity, price, costs)
            else:
                buckets[month]["out"] += sellFlow(quantity, price, costs)
        months = [
            {
                "month": month,
                "in": round(bucket["in"], 2),
                "out": round(bucket["out"], 2),
                "net": round(bucket["in"] - bucket["out"], 2),
            }
            for month, bucket in buckets.items()
        ]
        totalIn = round(sum(bucket["in"] for bucket in buckets.values()), 2)
        totalOut = round(sum(bucket["out"] for bucket in buckets.values()), 2)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "months": months,
            "total_in": totalIn,
            "total_out": totalOut,
            "net": round(totalIn - totalOut, 2),
        }

    @classmethod
    def getDividendsMonthly(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> dict:
        from main.app.wallet.wallets import WalletsManager

        WalletsManager.getWallet(db, walletId, userId)
        EarningsManager.maybeAutoSync(db, walletId, userId)
        earningRows = (
            db.query(Earning)
            .filter(Earning.walletId == walletId, Earning.payDate >= start, Earning.payDate <= end)
            .order_by(Earning.payDate, Earning.earningId)
            .all()
        )
        buckets: dict[str, dict] = {month: {"gross": 0.0, "net": 0.0, "count": 0} for month in monthRange(start, end)}
        for earningRow in earningRows:
            month = str(earningRow.payDate)[:7]
            buckets[month]["gross"] += float(earningRow.gross)
            buckets[month]["net"] += float(earningRow.netIrAdjusted)
            buckets[month]["count"] += 1
        months = [
            {
                "month": month,
                "gross": round(bucket["gross"], 2),
                "net": round(bucket["net"], 2),
                "count": bucket["count"],
            }
            for month, bucket in buckets.items()
        ]
        totalGross = round(sum(bucket["gross"] for bucket in buckets.values()), 2)
        totalNet = round(sum(bucket["net"] for bucket in buckets.values()), 2)
        return {
            "from": start.isoformat(),
            "to": end.isoformat(),
            "months": months,
            "total_gross": totalGross,
            "total_net": totalNet,
            "count": sum(bucket["count"] for bucket in buckets.values()),
        }
