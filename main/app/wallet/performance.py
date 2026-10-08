"""Time-weighted performance over the transaction ledger.

Metric semantics (explicit — reviewer #6, performance-owned portion):

- ``twr``: dividend-inclusive time-weighted return. Each held day earns
  ``(close - prevClose) / prevClose`` plus a dividend yield leg
  ``(grossPerShare / qtyAtEx) / prevClose`` on ex-dates, where ``qtyAtEx``
  replays the ledger up to that date (sells after ex keep the full yield).
  Daily cross-ticker returns aggregate value-weighted by ``qty x prevClose``;
  compounding is multiplicative. External contributions are neutral by
  construction (mid-window buys at market price leave single-ticker TWR
  unchanged — invariant-tested).
- ``price_return``: same machinery with the dividend leg removed.
- ``dividends_received``: sum of net (IR-adjusted) earnings whose ex-date
  falls in the window.
- ``volatility``: annualized stdev of daily total returns (x sqrt(252));
  0.0 with fewer than 2 scored days.
- ``twr_annualized``: ``(1 + twr) ** (365 / spanDays) - 1``.

Money/quantity/price/yield/weight math is :class:`~decimal.Decimal`
(coerced via entries.toDecimal, tolerant of legacy float snaps). ``float``
appears only for stdev/sqrt/power (inherently floating) and at the output
boundary.
"""

import logging
from datetime import date as dateType
from datetime import timedelta
from decimal import Decimal
from math import sqrt
from statistics import stdev
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.utils.sync_cache import sync_cache
from main.app.wallet.entries import EntriesManager, toDecimal
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning, Transaction, Wallet

logger = logging.getLogger(__name__)

PERFORMANCE_EPOCH = "1970-01-01T00:00:00"


class PerformanceManager:
    @classmethod
    @sync_cache(
        ttl="6h",
        key="wallet:performance:{userId}:{tickerKey}:{fromIso}:{toIso}:{recalcKey}:{entriesSnap}:{earningsSnap}:v3",
    )
    def cachedPerformance(
        cls,
        userId: int,
        tickerKey: str,
        fromIso: str,
        toIso: str,
        recalcKey: str,
        entriesSnap: tuple[tuple[str, str, str, str, str, str, int], ...],
        earningsSnap: tuple[tuple[str, str, str, str], ...],
    ) -> dict:
        del recalcKey

        if tickerKey:
            tickers = [tickerKey]
        else:
            universe = {entryTicker for entryTicker, _, _, _, _, _, _ in entriesSnap}
            universe.update(earnTicker for earnTicker, _, _, _ in earningsSnap)
            tickers = sorted(universe)

        perTickerDays: dict[str, dict[str, tuple[Decimal, Decimal, Decimal]]] = {}

        dividendsReceived = Decimal(0)
        for ticker in tickers:
            for earnTicker, exIso, _, netValue in earningsSnap:
                if earnTicker == ticker and fromIso <= exIso <= toIso:
                    dividendsReceived += toDecimal(netValue)

            series = PositionsManager.fetchPadraoCloses(ticker)

            tickerEntries = [
                (entryIso, entrySide, entryQty, entryPrice, entryCosts)
                for entryTicker, entryIso, entrySide, entryQty, entryPrice, entryCosts, _ in entriesSnap
                if entryTicker == ticker
            ]

            baselineRows = [
                SimpleNamespace(side=entrySide, quantity=entryQty, price=entryPrice, costs=entryCosts)
                for entryIso, entrySide, entryQty, entryPrice, entryCosts in tickerEntries
                if entryIso < fromIso
            ]

            positionQty, positionAvg = EntriesManager.applyEntries(Decimal(0), Decimal(0), baselineRows)

            pendingEntries = sorted(
                (
                    (
                        SimpleNamespace(side=entrySide, quantity=entryQty, price=entryPrice, costs=entryCosts),
                        entryIso,
                    )
                    for entryIso, entrySide, entryQty, entryPrice, entryCosts in tickerEntries
                    if fromIso <= entryIso <= toIso
                ),
                key=lambda pendingItem: pendingItem[1],
            )
            pendingIdx = 0

            closeByIso = {
                closeDay.isoformat(): toDecimal(closePrice)
                for closeDay, closePrice in series
                if fromIso <= closeDay.isoformat() <= toIso
            }

            windowDays = sorted(closeByIso)
            prevClose = None
            for seriesDay, seriesClose in series:
                if seriesDay.isoformat() < fromIso:
                    prevClose = toDecimal(seriesClose)
                else:
                    break

            dayMap: dict[str, tuple[Decimal, Decimal, Decimal]] = {}
            for dayIso in windowDays:
                while pendingIdx < len(pendingEntries) and pendingEntries[pendingIdx][1] <= dayIso:
                    pendingRow = pendingEntries[pendingIdx][0]
                    positionQty, positionAvg = EntriesManager.applyEntries(positionQty, positionAvg, [pendingRow])
                    pendingIdx += 1
                dayClose = closeByIso[dayIso]

                if positionQty > 0 and prevClose:
                    priceDay = (dayClose - prevClose) / prevClose
                    dividendYield = Decimal(0)

                    for earnTicker, exIso, grossValue, _ in earningsSnap:
                        if earnTicker == ticker and exIso == dayIso:
                            dividendYield += (toDecimal(grossValue) / positionQty) / prevClose
                    dayMap[dayIso] = (priceDay + dividendYield, priceDay, positionQty * prevClose)

                prevClose = dayClose
            perTickerDays[ticker] = dayMap

        allDays = sorted({dayIso for dayMap in perTickerDays.values() for dayIso in dayMap})

        dailyTotal: list[Decimal] = []
        dailyPrice: list[Decimal] = []
        for dayIso in allDays:
            weightTotal = sum((dayMap[dayIso][2] for dayMap in perTickerDays.values() if dayIso in dayMap), Decimal(0))
            if weightTotal > 0:
                dailyTotal.append(
                    sum(
                        (
                            dayMap[dayIso][0] * dayMap[dayIso][2]
                            for dayMap in perTickerDays.values()
                            if dayIso in dayMap
                        ),
                        Decimal(0),
                    )
                    / weightTotal
                )
                dailyPrice.append(
                    sum(
                        (
                            dayMap[dayIso][1] * dayMap[dayIso][2]
                            for dayMap in perTickerDays.values()
                            if dayIso in dayMap
                        ),
                        Decimal(0),
                    )
                    / weightTotal
                )

        twrTotal = Decimal(1)
        for dayReturn in dailyTotal:
            twrTotal *= 1 + dayReturn

        twrTotal -= 1
        priceTotal = Decimal(1)
        for priceDay in dailyPrice:
            priceTotal *= 1 + priceDay

        priceTotal -= 1
        spanDays = (dateType.fromisoformat(toIso) - dateType.fromisoformat(fromIso)).days
        if spanDays <= 0:
            annualizedValue = 0.0
        else:
            annualizedValue = float(1 + twrTotal) ** (365 / spanDays) - 1

        volatilityValue = float(stdev(dailyTotal)) * sqrt(252) if len(dailyTotal) >= 2 else 0.0

        return {
            "twr": float(twrTotal),
            "twr_annualized": annualizedValue,
            "volatility": volatilityValue,
            "dividends_received": float(dividendsReceived),
            "price_return": float(priceTotal),
        }

    @classmethod
    def defaultWindow(
        cls, db: Session, wallet: Wallet, start: dateType | None, end: dateType | None
    ) -> tuple[dateType, dateType]:
        # Fill omitted /performance bounds: lifetime window ending today.
        walletId = int(wallet.walletId)
        today = dateType.today()
        if start is None:
            firstRow = (
                db.query(Transaction.date).filter(Transaction.walletId == walletId).order_by(Transaction.date).first()
            )
            start = firstRow[0] if firstRow is not None else today - timedelta(days=365)
        if end is None:
            end = today
        return start, end

    @classmethod
    def resolveWindowFromIso(
        cls,
        db: Session,
        wallet: Wallet,
        fromIso: str | None,
        toIso: str | None,
    ) -> tuple[dateType, dateType]:
        try:
            start = dateType.fromisoformat(fromIso) if fromIso else None
            end = dateType.fromisoformat(toIso) if toIso else None
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid date, expected YYYY-MM-DD")
        return cls.defaultWindow(db, wallet, start, end)

    @classmethod
    def getPerformance(
        cls, db: Session, wallet: Wallet, ticker: str | None, startDate: dateType, endDate: dateType
    ) -> dict:
        walletId = int(wallet.walletId)
        userId = int(wallet.userId)
        recalcStamp = wallet.lastRecalc
        recalcKey = str(recalcStamp) if recalcStamp is not None else PERFORMANCE_EPOCH
        ledgerQuery = db.query(Transaction).filter(Transaction.walletId == walletId)
        if ticker:
            ledgerQuery = ledgerQuery.filter(Transaction.ticker == ticker)
        ledgerRows = ledgerQuery.order_by(Transaction.date, Transaction.entryId).all()
        entriesSnap = EntriesManager.snapshotEntries(ledgerRows)
        earningQuery = db.query(Earning).filter(Earning.walletId == walletId)
        if ticker:
            earningQuery = earningQuery.filter(Earning.ticker == ticker)
        earningRows = earningQuery.all()
        earningsSnap = tuple(
            (str(earningRow.ticker), str(earningRow.exDate), str(earningRow.gross), str(earningRow.netIrAdjusted))
            for earningRow in earningRows
        )
        return cls.cachedPerformance(
            userId, ticker or "", startDate.isoformat(), endDate.isoformat(), recalcKey, entriesSnap, earningsSnap
        )
