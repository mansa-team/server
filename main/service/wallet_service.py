import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime
from typing import Literal

import requests
from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import Config
from main.models.wallet import Holding, Target, Transaction, Wallet

logger = logging.getLogger(__name__)


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
    requireWalletOwnership(wallet.userId, {"userId": userId})
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
        holding.quantity = quantity
        holding.avgPrice = avg
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
    _get_owned_wallet(db, entry.walletId, userId)
    changes = patch.model_dump(exclude_unset=True)
    for fieldName, fieldValue in changes.items():
        if fieldValue is not None:
            setattr(entry, fieldName, fieldValue)
    db.flush()
    try:
        holding = recalc_holding(db, entry.walletId, entry.ticker)
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
    _get_owned_wallet(db, entry.walletId, userId)
    walletId = entry.walletId
    ticker = entry.ticker
    db.delete(entry)
    db.flush()
    try:
        holding = recalc_holding(db, walletId, ticker)
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
                params={"search": ticker, "compact": False},
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
    tickers = [holding.ticker for holding in holdings]
    prices = fetchLivePrices(tickers)
    for ticker, price in list(prices.items()):
        if price is None:
            prices[ticker] = fetchCachedClose(ticker)
    equities: dict[str, float | None] = {}
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(holding.ticker)
        if price is None:
            equities[holding.ticker] = None
        else:
            equities[holding.ticker] = holdingQuantity * price
    equityTotal = sum(equity for equity in equities.values() if equity is not None)
    items = []
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(holding.ticker)
        equity = equities[holding.ticker]
        if price is None or equity is None:
            currentPrice = None
            equityValue = None
            appreciation = None
        else:
            currentPrice = price
            equityValue = equity
            appreciation = equity - holdingQuantity * holdingAvg
        percentWallet = (equity / equityTotal * 100) if equity is not None and equityTotal else 0
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
