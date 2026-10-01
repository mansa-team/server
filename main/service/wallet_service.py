import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime
from functools import lru_cache
from math import sqrt
from statistics import stdev
from types import SimpleNamespace
from typing import Literal

import requests
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import Config
from main.models.wallet import Earning, Holding, Snapshot, Target, Transaction, Wallet

logger = logging.getLogger(__name__)

IR_RATE = {"Div": 0.0, "JSCP": 0.15, "RendTributado": 0.15}

TIPO_MAP = {
    "Dividendo": "Div",
    "JCP": "JSCP",
    "Juros Sobre Capital Proprio": "JSCP",
    "Rend. Tributado": "RendTributado",
}


def create_wallet(db: Session, userId: int, name: str) -> Wallet:
    wallet = Wallet(userId=userId, name=name)
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def list_wallets(db: Session, userId: int) -> list[Wallet]:
    return db.query(Wallet).filter(Wallet.userId == userId).all()


class EntryCreate(BaseModel):
    wallet_id: int
    side: Literal["Compra", "Venda"]
    asset_type: str
    ticker: str
    date: dateType
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    costs: float = Field(default=0.0, ge=0)


class EntryUpdate(BaseModel):
    date: dateType | None = None
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, ge=0)
    costs: float | None = Field(default=None, ge=0)


def _get_owned_wallet(db: Session, walletId: int, userId: int):
    from main.app.wallet.auth import requireWalletOwnership

    wallet = db.query(Wallet).filter(Wallet.walletId == walletId).first()
    if wallet is None:
        raise HTTPException(status_code=404, detail="wallet not found")
    requireWalletOwnership(int(wallet.userId), {"userId": userId})
    return wallet


def _apply_entries(quantity: float, avg: float, entries: list[Transaction]) -> tuple[float, float]:
    for entry in entries:
        entryQuantity = float(entry.quantity)
        entryPrice = float(entry.price)
        entryCosts = float(entry.costs)
        if entry.side == "Compra":
            total = quantity * avg + entryQuantity * entryPrice + entryCosts
            quantity += entryQuantity
            avg = total / quantity
        else:
            if entryQuantity > quantity:
                raise HTTPException(status_code=422, detail="sell exceeds holding")
            quantity -= entryQuantity
    return quantity, avg


def recalc_holding(db: Session, walletId: int, ticker: str) -> Holding | None:
    entries = (
        db.query(Transaction)
        .filter(Transaction.walletId == walletId, Transaction.ticker == ticker)
        .order_by(Transaction.date, Transaction.entryId)
        .all()
    )
    holding = db.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == ticker).first()
    if not entries:
        if holding is not None:
            db.delete(holding)
        return None
    quantity, avg = _apply_entries(0.0, 0.0, entries)
    if holding is None:
        holding = Holding(
            walletId=walletId, assetType=entries[0].assetType, ticker=ticker, quantity=quantity, avgPrice=avg
        )
        db.add(holding)
    else:
        holding.quantity = quantity  # type: ignore[assignment]
        holding.avgPrice = avg  # type: ignore[assignment]
    return holding


def add_entry(db: Session, userId: int, data: EntryCreate) -> tuple[Transaction, Holding | None]:
    _get_owned_wallet(db, data.wallet_id, userId)
    if data.side == "Venda":
        holding = db.query(Holding).filter(Holding.walletId == data.wallet_id, Holding.ticker == data.ticker).first()
        if holding is None or data.quantity > float(holding.quantity):
            raise HTTPException(status_code=422, detail="sell exceeds holding")
    entry = Transaction(
        walletId=data.wallet_id,
        side=data.side,
        assetType=data.asset_type,
        ticker=data.ticker,
        date=data.date,
        quantity=data.quantity,
        price=data.price,
        costs=data.costs,
    )
    db.add(entry)
    db.flush()
    holding = recalc_holding(db, data.wallet_id, data.ticker)
    db.commit()
    db.refresh(entry)
    if holding is not None:
        db.refresh(holding)
    return entry, holding


def list_entries(
    db: Session, userId: int, walletId: int, ticker: str | None = None, limit: int = 20, offset: int = 0
) -> tuple[int, list[Transaction]]:
    _get_owned_wallet(db, walletId, userId)
    query = db.query(Transaction).filter(Transaction.walletId == walletId)
    if ticker is not None:
        query = query.filter(Transaction.ticker == ticker)
    total = query.count()
    items = query.order_by(Transaction.date, Transaction.entryId).offset(offset).limit(limit).all()
    return total, items


def update_entry(db: Session, userId: int, entryId: int, patch: EntryUpdate) -> tuple[Transaction, Holding | None]:
    entry = db.query(Transaction).filter(Transaction.entryId == entryId).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    _get_owned_wallet(db, int(entry.walletId), userId)
    changes = patch.model_dump(exclude_unset=True)
    for fieldName, fieldValue in changes.items():
        if fieldValue is not None:
            setattr(entry, fieldName, fieldValue)
    db.flush()
    try:
        holding = recalc_holding(db, int(entry.walletId), str(entry.ticker))
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    db.refresh(entry)
    if holding is not None:
        db.refresh(holding)
    return entry, holding


def delete_entry(db: Session, userId: int, entryId: int) -> tuple[int, Holding | None]:
    entry = db.query(Transaction).filter(Transaction.entryId == entryId).first()
    if entry is None:
        raise HTTPException(status_code=404, detail="entry not found")
    _get_owned_wallet(db, int(entry.walletId), userId)
    walletId = entry.walletId
    ticker = entry.ticker
    db.delete(entry)
    db.flush()
    try:
        holding = recalc_holding(db, int(walletId), str(ticker))
    except HTTPException:
        db.rollback()
        raise
    db.commit()
    return entryId, holding


STOCKS_TIMEOUT = 3


def stocksApiBase() -> str:
    return f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}"


def stocksApiHeaders() -> dict:
    key = os.getenv("STOCKS_API_KEY", "")
    return {"X-API-Key": key} if key else {}


def fetchLivePrices(tickers: list[str]) -> dict[str, float | None]:
    if not tickers:
        return {}

    def one(ticker: str) -> tuple[str, float | None]:
        try:
            resp = requests.get(
                f"{stocksApiBase()}/stocks/cotations/live",
                params={"search": ticker, "compact": False},  # type: ignore[arg-type]
                headers=stocksApiHeaders(),
                timeout=STOCKS_TIMEOUT,
            )
            if resp.status_code == 429:
                logger.warning("Live price quota exhausted for %s", ticker)
                return ticker, None
            if resp.status_code != 200:
                return ticker, None
            return ticker, float(resp.json()["data"][0]["PRECO ATUAL"])
        except Exception:
            return ticker, None

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
        return dict(pool.map(one, tickers))


def fetchCachedClose(ticker: str) -> float | None:
    try:
        resp = requests.get(
            f"{stocksApiBase()}/stocks/cotations",
            params={"search": ticker},
            headers=stocksApiHeaders(),
            timeout=STOCKS_TIMEOUT,
        )
        if resp.status_code == 429:
            logger.warning("Cached close quota exhausted for %s", ticker)
            return None
        if resp.status_code != 200:
            return None
        rows = resp.json()["data"]
        latest = max(rows, key=lambda row: datetime.strptime(row["DATA"], "%d-%m-%Y"))
        return float(latest["PRECO"])
    except Exception:
        return None


def get_positions(db: Session, walletId: int, userId: int) -> dict:
    _get_owned_wallet(db, walletId, userId)
    holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
    tickers = [str(holding.ticker) for holding in holdings]
    prices = fetchLivePrices(tickers)
    for ticker, price in list(prices.items()):
        if price is None:
            prices[ticker] = fetchCachedClose(ticker)
    equities: dict[str, float | None] = {}
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(str(holding.ticker))
        if price is None:
            equities[str(holding.ticker)] = None
        else:
            equities[str(holding.ticker)] = holdingQuantity * price
    equityTotal = sum(equity for equity in equities.values() if equity is not None)
    items = []
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(str(holding.ticker))
        equity = equities[str(holding.ticker)]
        if price is None or equity is None:
            currentPrice = None
            equityValue = None
            appreciation = None
        else:
            currentPrice = price
            equityValue = equity
            appreciation = equity - holdingQuantity * holdingAvg
        percentWallet = (equity / equityTotal) if equity is not None and equityTotal else 0
        target = (
            db.query(Target)
            .filter(Target.walletId == walletId, Target.keyKind == "ticker", Target.keyValue == holding.ticker)
            .first()
        )
        percentIdeal = float(target.percentIdeal) if target is not None else None
        holdingRating = holding.rating
        buyFlag = (
            percentIdeal is not None and percentWallet < percentIdeal and (holdingRating is None or holdingRating >= 6)
        )
        items.append(
            {
                "ticker": holding.ticker,
                "quantity": holdingQuantity,
                "avgPrice": holdingAvg,
                "current_price": currentPrice,
                "equity": equityValue,
                "appreciation": appreciation,
                "percent_wallet": percentWallet,
                "percent_ideal": percentIdeal,
                "buy_flag": buyFlag,
            }
        )
    return {"items": items, "equity_total": equityTotal}


class TargetUpsert(BaseModel):
    wallet_id: int
    key_kind: Literal["ticker", "group"]
    key_value: str
    percent_ideal: float = Field(ge=0, le=100)


class RatingUpsert(BaseModel):
    wallet_id: int
    ticker: str
    rating: int = Field(ge=0, le=10)


def get_summary(db: Session, walletId: int, userId: int) -> dict:
    wallet = _get_owned_wallet(db, walletId, userId)
    holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
    applied = sum(float(holding.quantity) * float(holding.avgPrice) for holding in holdings)
    tickers = [str(holding.ticker) for holding in holdings]
    prices = fetchLivePrices(tickers)
    for ticker, price in list(prices.items()):
        if price is None:
            prices[ticker] = fetchCachedClose(ticker)
    equity = 0.0
    for holding in holdings:
        price = prices.get(str(holding.ticker))
        if price is not None:
            equity += float(holding.quantity) * price
    variation = equity - applied
    today = dateType.today()
    snapshot = db.query(Snapshot).filter(Snapshot.walletId == walletId, Snapshot.date == today).first()
    if snapshot is None:
        snapshot = Snapshot(
            walletId=walletId,
            date=today,
            applied=applied,
            equity=equity,
            variation=variation,
            profitTwr=None,
            profitAmount=variation,
            profitTwr12m=None,
            profitTwr12mAmount=variation,
        )
        db.add(snapshot)
    else:
        snapshot.applied = applied  # type: ignore[assignment]
        snapshot.equity = equity  # type: ignore[assignment]
        snapshot.variation = variation  # type: ignore[assignment]
        snapshot.profitTwr = None  # type: ignore[assignment]
        snapshot.profitAmount = variation  # type: ignore[assignment]
        snapshot.profitTwr12m = None  # type: ignore[assignment]
        snapshot.profitTwr12mAmount = variation  # type: ignore[assignment]
    wallet.lastRecalc = datetime.now()
    db.commit()
    return {
        "applied": applied,
        "equity": equity,
        "variation": variation,
        "profit_twr": None,
        "profit_amount": variation,
        "profit_twr_12m": None,
        "profit_twr_12m_amount": variation,
    }


def get_allocation(db: Session, walletId: int, userId: int, groupBy: str) -> dict:
    _get_owned_wallet(db, walletId, userId)
    holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
    tickers = [str(holding.ticker) for holding in holdings]
    prices = fetchLivePrices(tickers)
    for ticker, price in list(prices.items()):
        if price is None:
            prices[ticker] = fetchCachedClose(ticker)
    groupEquity: dict[str, float] = {}
    for holding in holdings:
        price = prices.get(str(holding.ticker))
        holdingEquity = float(holding.quantity) * price if price is not None else 0.0
        groupKey = str(holding.ticker) if groupBy == "ticker" else str(holding.assetType)
        groupEquity[groupKey] = groupEquity.get(groupKey, 0.0) + holdingEquity
    equityTotal = sum(groupEquity.values())
    items = [
        {
            "key": groupKey,
            "equity": groupValue,
            "pct": (groupValue / equityTotal) if equityTotal else 0,
        }
        for groupKey, groupValue in groupEquity.items()
    ]
    return {"items": items, "equity_total": equityTotal}


def upsert_target(db: Session, userId: int, data: TargetUpsert) -> Target:
    _get_owned_wallet(db, data.wallet_id, userId)
    target = (
        db.query(Target)
        .filter(
            Target.walletId == data.wallet_id,
            Target.keyKind == data.key_kind,
            Target.keyValue == data.key_value,
        )
        .first()
    )
    if target is None:
        target = Target(
            walletId=data.wallet_id,
            keyKind=data.key_kind,
            keyValue=data.key_value,
            percentIdeal=data.percent_ideal,
        )
        db.add(target)
    else:
        target.percentIdeal = data.percent_ideal  # type: ignore[assignment]
    db.commit()
    db.refresh(target)
    return target


def set_rating(db: Session, userId: int, data: RatingUpsert) -> Holding:
    _get_owned_wallet(db, data.wallet_id, userId)
    holding = db.query(Holding).filter(Holding.walletId == data.wallet_id, Holding.ticker == data.ticker).first()
    if holding is None:
        raise HTTPException(status_code=404, detail="holding not found")
    holding.rating = data.rating  # type: ignore[assignment]
    db.commit()
    db.refresh(holding)
    return holding


def position_at_date(entries: list[Transaction], exDate: dateType) -> float:
    # str() trick: Column-typed dates compare mypy-clean as ISO strings (lexicographic == chronological).
    datedEntries = [entry for entry in entries if str(entry.date) <= exDate.isoformat()]
    quantity, _ = _apply_entries(0.0, 0.0, datedEntries)
    return quantity


def fetchMarketDividends(ticker: str) -> list[dict]:
    try:
        resp = requests.get(
            f"{stocksApiBase()}/stocks/fundamental",
            params={"search": ticker, "fields": "HISTORICO DIVIDENDOS"},  # type: ignore[arg-type]
            headers=stocksApiHeaders(),
            timeout=STOCKS_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        payload = resp.json()["data"]
        if payload and isinstance(payload[0], dict) and "HISTORICO DIVIDENDOS" in payload[0]:
            return payload[0]["HISTORICO DIVIDENDOS"]
        return payload
    except Exception:
        return []


def sync_earnings(db: Session, walletId: int, userId: int) -> dict:
    _get_owned_wallet(db, walletId, userId)
    today = dateType.today()
    accrued = 0
    skippedUnknown: list[str] = []
    holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
    for holding in holdings:
        if float(holding.quantity) <= 0:
            continue
        holdingTicker = str(holding.ticker)
        ledgerEntries = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId, Transaction.ticker == holdingTicker)
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        for record in fetchMarketDividends(holdingTicker):
            label = str(record.get("TIPO PROVENTO"))
            kind = TIPO_MAP.get(label)
            if kind is None:
                if label not in skippedUnknown:
                    skippedUnknown.append(label)
                continue
            try:
                exDate = datetime.strptime(record["DATA COM"], "%d-%m-%Y").date()
                payDate = datetime.strptime(record["DATA PAGAMENTO"], "%d-%m-%Y").date()
                perShare = float(record["VALOR AJUSTADO"])
            except Exception:
                continue
            quantityAtEx = position_at_date(ledgerEntries, exDate)
            if quantityAtEx <= 0:
                continue
            existing = (
                db.query(Earning)
                .filter(
                    Earning.walletId == walletId,
                    Earning.ticker == holdingTicker,
                    Earning.exDate == exDate,
                    Earning.kind == kind,
                )
                .first()
            )
            if existing is not None:
                continue
            gross = perShare * quantityAtEx
            earning = Earning(
                walletId=walletId,
                ticker=holdingTicker,
                kind=kind,
                exDate=exDate,
                payDate=payDate,
                gross=gross,
                netIrAdjusted=gross * (1 - IR_RATE[kind]),
                status="Recebido" if payDate <= today else "A Receber",
            )
            db.add(earning)
            accrued += 1
    transitioned = 0
    pending = db.query(Earning).filter(Earning.walletId == walletId, Earning.status == "A Receber").all()
    for earning in pending:
        if str(earning.payDate) <= today.isoformat():
            earning.status = "Recebido"  # type: ignore[assignment]
            transitioned += 1
    db.commit()
    return {"accrued": accrued, "transitioned": transitioned, "skipped_unknown": skippedUnknown}


def list_earnings(db: Session, walletId: int, userId: int, status: str | None = None) -> list[Earning]:
    _get_owned_wallet(db, walletId, userId)
    query = db.query(Earning).filter(Earning.walletId == walletId)
    if status is not None:
        query = query.filter(Earning.status == status)
    return query.order_by(Earning.exDate, Earning.earningId).all()


PERFORMANCE_EPOCH = "1970-01-01T00:00:00"


def fetchPadraoCloses(ticker: str) -> list[tuple[dateType, float]]:
    try:
        resp = requests.get(
            f"{stocksApiBase()}/stocks/cotations",
            params={"search": ticker},
            headers=stocksApiHeaders(),
            timeout=STOCKS_TIMEOUT,
        )
        if resp.status_code != 200:
            return []
        parsedCloses: list[tuple[dateType, float]] = []
        for closeRow in resp.json()["data"]:
            try:
                parsedCloses.append((datetime.strptime(closeRow["DATA"], "%d-%m-%Y").date(), float(closeRow["PRECO"])))
            except Exception:
                continue
        parsedCloses.sort(key=lambda closeItem: closeItem[0])
        return parsedCloses
    except Exception:
        return []


@lru_cache(maxsize=1024)
def _cachedPerformance(
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
        positionQty, positionAvg = _apply_entries(0.0, 0.0, baselineRows)  # type: ignore[arg-type]
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
                positionQty, positionAvg = _apply_entries(positionQty, positionAvg, [datedRow])  # type: ignore[arg-type]
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


def get_performance(
    db: Session, walletId: int, userId: int, ticker: str | None, startDate: dateType, endDate: dateType
) -> dict:
    wallet = _get_owned_wallet(db, walletId, userId)
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
    return _cachedPerformance(
        walletId, ticker or "", startDate.isoformat(), endDate.isoformat(), recalcKey, entriesSnap, earningsSnap
    )
