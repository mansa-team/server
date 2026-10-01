import logging
from datetime import date as dateType
from functools import lru_cache
from math import sqrt
from statistics import stdev
from types import SimpleNamespace

from sqlalchemy.orm import Session

from main.app.wallet.entries import applyEntries
from main.app.wallet.market_data import fetchPadraoCloses
from main.app.wallet.wallets import getWallet
from main.models.wallet import Earning, Transaction

logger = logging.getLogger(__name__)

PERFORMANCE_EPOCH = "1970-01-01T00:00:00"


@lru_cache(maxsize=1024)
def cachedPerformance(
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

        series = fetchPadraoCloses(ticker)

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

        positionQty, positionAvg = applyEntries(0.0, 0.0, baselineRows)  # type: ignore[arg-type]

        entriesByDay: dict[str, list] = {}
        for entryIso, entrySide, entryQty, entryPrice, entryCosts in tickerEntries:
            if fromIso <= entryIso <= toIso:
                entriesByDay.setdefault(entryIso, []).append(
                    SimpleNamespace(side=entrySide, quantity=entryQty, price=entryPrice, costs=entryCosts)
                )

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
            for datedRow in entriesByDay.get(dayIso, []):
                positionQty, positionAvg = applyEntries(positionQty, positionAvg, [datedRow])  # type: ignore[arg-type]
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


def getPerformance(
    db: Session, walletId: int, userId: int, ticker: str | None, startDate: dateType, endDate: dateType
) -> dict:
    wallet = getWallet(db, walletId, userId)
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
    return cachedPerformance(
        walletId, ticker or "", startDate.isoformat(), endDate.isoformat(), recalcKey, entriesSnap, earningsSnap
    )
