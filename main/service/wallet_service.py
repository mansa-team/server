import logging
from datetime import date as dateType
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from main.models.wallet import Holding, Transaction, Wallet

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
