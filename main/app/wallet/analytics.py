"""Ledger-derived progression, cash flows and dividend rollups.

Metric semantics (explicit — reviewer #6, analytics-owned portion):

- ``invested`` (progression): net cash applied = sum over buys of
  ``qty x price + costs`` minus, over sells, net proceeds
  ``qty x price - costs``. This is cumulative cash in/out, NOT remaining
  cost basis (a sale at a gain drives ``invested`` below cost basis).
- ``equity`` (progression): ``qty x lastClose`` per ticker, summed.
- Cash-flow rows: ``in`` = ``qty x price + costs`` on buys (0 on sells);
  ``out`` = ``qty x price - costs`` on sells (0 on buys). Selling costs
  reduce proceeds; they are not booked separately (reviewer #7).
- Dividends monthly: stored earnings grouped by ``payDate``; ``gross`` as
  accrued, ``net`` IR-adjusted (Div x1.0, JSCP/RendTributado x0.85).

Money/quantity math is :class:`~decimal.Decimal`; ``float`` only at the
point/row output boundary.
"""

import logging
from datetime import date as dateType
from decimal import Decimal

from sqlalchemy.orm import Session

from main.utils.sync_cache import sync_cache
from main.app.wallet.earnings import EarningsManager
from main.app.wallet.entries import EntriesManager, toDecimal
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning, Transaction, Wallet

logger = logging.getLogger(__name__)

PROGRESSION_EPOCH = "1970-01-01T00:00:00"
MAX_POINTS = 2000


class AnalyticsManager:
    @classmethod
    @sync_cache(
        ttl="6h",
        key="wallet:progression:{userId}:{fromIso}:{toIso}:{recalcKey}:{entriesSnap}",
    )
    def cachedProgression(
        cls,
        userId: int,
        fromIso: str,
        toIso: str,
        recalcKey: str,
        entriesSnap: tuple[tuple[str, str, str, str, str, str, int], ...],
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
                (entryIso, entrySide, toDecimal(entryQty), toDecimal(entryPrice), toDecimal(entryCosts), entryId)
            )
        for tickerRows in entriesByTicker.values():
            tickerRows.sort()

        firstEntryIso = min(entryIso for _, entryIso, _, _, _, _, _ in entriesSnap)

        state: dict[str, dict] = {
            ticker: {
                "qty": Decimal(0),
                "invested": Decimal(0),
                "entryIdx": 0,
                "closeIdx": 0,
                "lastClose": None,
            }
            for ticker in tickers
        }
        points = []
        for dayIso in sampleDays:
            if dayIso < firstEntryIso:
                continue
            equity = Decimal(0)
            invested = Decimal(0)
            for ticker in tickers:
                tickerState = state[ticker]

                rows = entriesByTicker.get(ticker, [])
                while tickerState["entryIdx"] < len(rows) and rows[tickerState["entryIdx"]][0] <= dayIso:
                    _, entrySide, entryQty, entryPrice, entryCosts, _ = rows[tickerState["entryIdx"]]
                    if entrySide == "Compra":
                        tickerState["qty"] += entryQty
                        tickerState["invested"] += entryQty * entryPrice + entryCosts
                    else:
                        tickerState["qty"] -= entryQty
                        tickerState["invested"] -= entryQty * entryPrice - entryCosts
                    tickerState["entryIdx"] += 1

                series = closesByTicker[ticker]
                while (
                    tickerState["closeIdx"] < len(series) and series[tickerState["closeIdx"]][0].isoformat() <= dayIso
                ):
                    tickerState["lastClose"] = toDecimal(series[tickerState["closeIdx"]][1])
                    tickerState["closeIdx"] += 1
                if tickerState["lastClose"] is not None:
                    equity += tickerState["qty"] * tickerState["lastClose"]
                invested += tickerState["invested"]
            points.append({"date": dayIso, "equity": float(equity), "invested": float(invested)})
        return {"granularity": "daily", "from": fromIso, "to": toIso, "points": points}

    @classmethod
    def getProgression(cls, db: Session, wallet: Wallet, start: dateType, end: dateType) -> dict:

        walletId = int(wallet.walletId)
        userId = int(wallet.userId)
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
        entriesSnap = EntriesManager.snapshotEntries(ledgerRows)
        return cls.cachedProgression(userId, start.isoformat(), end.isoformat(), recalcKey, entriesSnap)

    @classmethod
    def getCashflows(cls, db: Session, wallet: Wallet, start: dateType, end: dateType) -> dict:

        walletId = int(wallet.walletId)
        ledgerRows = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId, Transaction.date >= start, Transaction.date <= end)  # type: ignore[arg-type]
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        rows = []
        for ledgerRow in ledgerRows:
            quantity, price, costs = (
                toDecimal(ledgerRow.quantity),
                toDecimal(ledgerRow.price),
                toDecimal(ledgerRow.costs),
            )
            if ledgerRow.side == "Compra":
                flowIn, flowOut = quantity * price + costs, Decimal(0)
            else:
                flowIn, flowOut = Decimal(0), quantity * price - costs
            rows.append(
                {
                    "date": str(ledgerRow.date),
                    "side": str(ledgerRow.side),
                    "ticker": str(ledgerRow.ticker),
                    "quantity": float(quantity),
                    "price": float(price),
                    "costs": float(costs),
                    "in": float(flowIn),
                    "out": float(flowOut),
                }
            )
        return {"from": start.isoformat(), "to": end.isoformat(), "rows": rows}

    @classmethod
    def getDividendsMonthly(cls, db: Session, wallet: Wallet, start: dateType, end: dateType) -> dict:

        walletId = int(wallet.walletId)
        EarningsManager.maybeAutoSync(db, wallet)
        earningRows = (
            db.query(Earning)
            .filter(Earning.walletId == walletId, Earning.payDate >= start, Earning.payDate <= end)  # type: ignore[arg-type]
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
