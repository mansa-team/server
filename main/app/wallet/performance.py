import logging
from datetime import date as dateType
from datetime import timedelta
from math import sqrt
from statistics import stdev
from types import SimpleNamespace
from typing import Literal

from cashews import cache as cashewsCache
from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.app.stocks_api.sync_cache import cache as walletCache
from main.app.wallet.entries import EntriesManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Earning, Transaction

logger = logging.getLogger(__name__)

cashewsCache.setup("mem://")

PERFORMANCE_EPOCH = "1970-01-01T00:00:00"

Preset = Literal["1M", "3M", "6M", "1A", "YTD", "TOTAL"]
PRESETS = frozenset({"1M", "3M", "6M", "1A", "YTD", "TOTAL"})
PRESET_DAYS = {"1M": 30, "3M": 91, "6M": 182, "1A": 365}
METRICS = frozenset({"twr", "twr_annualized", "volatility", "dividends_received", "price_return"})


class PerformanceManager:
    @classmethod
    @walletCache(
        ttl="6h",
        key="wallet:performance:{walletId}:{tickerKey}:{fromIso}:{toIso}:{recalcKey}:{entriesSnap}:{earningsSnap}:v2",
    )
    def cachedPerformance(
        cls,
        walletId: int,
        tickerKey: str,
        fromIso: str,
        toIso: str,
        recalcKey: str,
        entriesSnap: tuple[tuple[str, str, str, float, float, float, int], ...],
        earningsSnap: tuple[tuple[str, str, float, float], ...],
    ) -> dict:
        del recalcKey

        if tickerKey:
            tickers = [tickerKey]
        else:
            universe = {entryTicker for entryTicker, _, _, _, _, _, _ in entriesSnap}
            universe.update(earnTicker for earnTicker, _, _, _ in earningsSnap)
            tickers = sorted(universe)

        perTickerDays: dict[str, dict[str, tuple[float, float, float]]] = {}

        dividendsReceived = 0.0
        for ticker in tickers:
            for earnTicker, exIso, _, netValue in earningsSnap:
                if earnTicker == ticker and fromIso <= exIso <= toIso:
                    dividendsReceived += netValue

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

            positionQty, positionAvg = EntriesManager.applyEntries(0.0, 0.0, baselineRows)  # type: ignore[arg-type]

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
                closeDay.isoformat(): closePrice
                for closeDay, closePrice in series
                if fromIso <= closeDay.isoformat() <= toIso
            }

            windowDays = sorted(closeByIso)
            prevClose = None
            for seriesDay, seriesClose in series:
                if seriesDay.isoformat() < fromIso:
                    prevClose = seriesClose
                else:
                    break

            dayMap: dict[str, tuple[float, float, float]] = {}
            for dayIso in windowDays:
                while pendingIdx < len(pendingEntries) and pendingEntries[pendingIdx][1] <= dayIso:
                    pendingRow = pendingEntries[pendingIdx][0]
                    positionQty, positionAvg = EntriesManager.applyEntries(positionQty, positionAvg, [pendingRow])  # type: ignore[arg-type]
                    pendingIdx += 1
                dayClose = closeByIso[dayIso]

                if positionQty > 0 and prevClose:
                    priceDay = (dayClose - prevClose) / prevClose
                    dividendYield = 0.0

                    for earnTicker, exIso, grossValue, _ in earningsSnap:
                        if earnTicker == ticker and exIso == dayIso:
                            dividendYield += (grossValue / positionQty) / prevClose
                    dayMap[dayIso] = (priceDay + dividendYield, priceDay, positionQty * prevClose)

                prevClose = dayClose
            perTickerDays[ticker] = dayMap

        allDays = sorted({dayIso for dayMap in perTickerDays.values() for dayIso in dayMap})

        dailyTotal: list[float] = []
        dailyPrice: list[float] = []
        for dayIso in allDays:
            weightTotal = sum(dayMap[dayIso][2] for dayMap in perTickerDays.values() if dayIso in dayMap)
            if weightTotal > 0:
                dailyTotal.append(
                    sum(dayMap[dayIso][0] * dayMap[dayIso][2] for dayMap in perTickerDays.values() if dayIso in dayMap)
                    / weightTotal
                )
                dailyPrice.append(
                    sum(dayMap[dayIso][1] * dayMap[dayIso][2] for dayMap in perTickerDays.values() if dayIso in dayMap)
                    / weightTotal
                )

        twrValue = 1.0
        for dayReturn in dailyTotal:
            twrValue *= 1 + dayReturn

        twrValue -= 1
        priceValue = 1.0
        for priceDay in dailyPrice:
            priceValue *= 1 + priceDay

        priceValue -= 1
        spanDays = (dateType.fromisoformat(toIso) - dateType.fromisoformat(fromIso)).days
        if spanDays <= 0:
            annualizedValue = 0.0
        else:
            annualizedValue = (1 + twrValue) ** (365 / spanDays) - 1

        volatilityValue = stdev(dailyTotal) * sqrt(252) if len(dailyTotal) >= 2 else 0.0

        return {
            "twr": twrValue,
            "twr_annualized": annualizedValue,
            "volatility": volatilityValue,
            "dividends_received": dividendsReceived,
            "price_return": priceValue,
        }

    @classmethod
    def defaultWindow(
        cls, db: Session, walletId: int, userId: int, start: dateType | None, end: dateType | None
    ) -> tuple[dateType, dateType]:
        # Fill omitted /performance bounds: lifetime window ending today.
        WalletsManager.getWallet(db, walletId, userId)
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
    def resolveWindow(
        cls,
        db: Session,
        walletId: int,
        userId: int,
        start: dateType | None,
        end: dateType | None,
        preset: str | None,
    ) -> tuple[dateType, dateType]:
        if preset is not None:
            today = dateType.today()
            if preset == "YTD":
                start = start or dateType(today.year, 1, 1)
                end = end or today
            elif preset != "TOTAL":
                end = end or today
                start = start or (end - timedelta(days=PRESET_DAYS[preset]))
        return cls.defaultWindow(db, walletId, userId, start, end)

    @classmethod
    def resolveWindowFromIso(
        cls,
        db: Session,
        walletId: int,
        userId: int,
        fromIso: str | None,
        toIso: str | None,
        preset: str | None = None,
    ) -> tuple[dateType, dateType]:
        try:
            start = dateType.fromisoformat(fromIso) if fromIso else None
            end = dateType.fromisoformat(toIso) if toIso else None
        except ValueError:
            raise HTTPException(status_code=422, detail="invalid date, expected YYYY-MM-DD")
        return cls.resolveWindow(db, walletId, userId, start, end, preset)

    @classmethod
    def selectMetrics(cls, body: dict, metrics: str | None) -> dict:
        if not metrics:
            return body
        picked = [metric.strip() for metric in metrics.split(",") if metric.strip()]
        unknown = [metric for metric in picked if metric not in METRICS]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"unknown metric(s) {', '.join(unknown)}, expected subset of: {', '.join(sorted(METRICS))}",
            )
        return {key: body[key] for key in picked}

    @classmethod
    def getPerformance(
        cls, db: Session, walletId: int, userId: int, ticker: str | None, startDate: dateType, endDate: dateType
    ) -> dict:
        wallet = WalletsManager.getWallet(db, walletId, userId)
        recalcStamp = wallet.lastRecalc
        recalcKey = str(recalcStamp) if recalcStamp is not None else PERFORMANCE_EPOCH
        ledgerQuery = db.query(Transaction).filter(Transaction.walletId == walletId)
        if ticker:
            ledgerQuery = ledgerQuery.filter(Transaction.ticker == ticker)
        ledgerRows = ledgerQuery.order_by(Transaction.date, Transaction.entryId).all()
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
        earningQuery = db.query(Earning).filter(Earning.walletId == walletId)
        if ticker:
            earningQuery = earningQuery.filter(Earning.ticker == ticker)
        earningRows = earningQuery.all()
        earningsSnap = tuple(
            (str(earningRow.ticker), str(earningRow.exDate), float(earningRow.gross), float(earningRow.netIrAdjusted))
            for earningRow in earningRows
        )
        return cls.cachedPerformance(
            walletId, ticker or "", startDate.isoformat(), endDate.isoformat(), recalcKey, entriesSnap, earningsSnap
        )
