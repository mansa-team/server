"""Ledger-sourced holdings and cost-basis engine.

Cost-basis semantics (explicit — reviewer #7, entries-owned portion):

- Buy cost = quantity x price + costs. Costs are capitalized into the
  average: ``avg = (qty*avg + buyQty*buyPrice + buyCosts) / newQty``.
- Sell does NOT change the average price. Sale proceeds are net of costs
  (``qty*price - costs``); realized P&L per sale = proceeds - qty x avg.
- Unrealized P&L = ``qty x (market - avg)`` (market from positions pass).
- TWR treats costs as above (buy costs raise the invested base; sell costs
  reduce proceeds); cash-flow legs mirror this (see analytics.py).

All domain math uses :class:`~decimal.Decimal`. ``float`` appears only at
the API/serialization boundary (pydantic inputs, ``serialize_*`` outputs).
Callers inside the domain (e.g. summary.ledgerPositions) receive Decimals.
"""

import logging
from collections.abc import Sequence
from datetime import date as dateType
from decimal import Decimal
from typing import Any, Literal, get_args

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Column
from sqlalchemy.orm import Session

from main.app.wallet.positions import PositionsManager
from main.models.wallet import Holding, Transaction, Wallet

logger = logging.getLogger(__name__)

AssetType = Literal["ACOES", "OUTROS"]
ALLOWED_ASSET_TYPES = frozenset(get_args(AssetType))

NUMERIC_PATCH_FIELDS = frozenset({"quantity", "price", "costs"})


def toDecimal(value: Decimal | float | int | str | Column[Decimal]) -> Decimal:
    """Coerce a DB/API numeric to Decimal via its shortest repr.

    ``Decimal(str(floatValue))`` keeps the human-meaningful value (0.1 stays
    0.1) instead of inheriting binary float error. Malformed input raises
    (never silently becomes a fallback figure).
    """
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def serialize_holding(holding) -> dict | None:
    if holding is None:
        return None
    return {"ticker": holding.ticker, "quantity": float(holding.quantity), "avgPrice": float(holding.avgPrice)}


# Kept: public API serialization used by wallet_controller — keep.
def serialize_entry(entry) -> dict:
    return {
        "entryId": entry.entryId,
        "wallet_id": entry.walletId,
        "side": entry.side,
        "asset_type": entry.assetType,
        "ticker": entry.ticker,
        "date": entry.date.isoformat(),
        "quantity": float(entry.quantity),
        "price": float(entry.price),
        "costs": float(entry.costs),
    }


class EntryCreate(BaseModel):
    side: Literal["Compra", "Venda"]
    asset_type: AssetType
    ticker: str
    date: dateType
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    costs: float = Field(default=0.0, ge=0)


class EntryUpdate(BaseModel):
    side: Literal["Compra", "Venda"] | None = None
    asset_type: AssetType | None = None
    date: dateType | None = None
    quantity: float | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, ge=0)
    costs: float | None = Field(default=None, ge=0)


class EntriesManager:
    @classmethod
    def snapshotEntries(cls, rows: list[Transaction]) -> tuple[tuple[str, str, str, str, str, str, int], ...]:
        # Numerics travel as shortest-repr strings: Decimal-exact and stable
        # as cache-key material. Consumers coerce via toDecimal.
        return tuple(
            (
                str(ledgerRow.ticker),
                str(ledgerRow.date),
                str(ledgerRow.side),
                str(ledgerRow.quantity),
                str(ledgerRow.price),
                str(ledgerRow.costs),
                int(ledgerRow.entryId),
            )
            for ledgerRow in rows
        )

    @classmethod
    def applyEntries(
        cls, quantity: Decimal | float, avg: Decimal | float, entries: Sequence[Any]
    ) -> tuple[Decimal, Decimal]:
        # Seeds accept float (cross-lane callers) but every step below is
        # Decimal: buy basis = qty*price + costs capitalized into avg; sell
        # only reduces quantity (avg untouched), oversell rejected.
        runningQty = toDecimal(quantity)
        runningAvg = toDecimal(avg)
        for entry in entries:
            entryQuantity = toDecimal(entry.quantity)
            entryPrice = toDecimal(entry.price)
            entryCosts = toDecimal(entry.costs)

            if entry.side == "Compra":
                total = runningQty * runningAvg + entryQuantity * entryPrice + entryCosts
                runningQty += entryQuantity
                runningAvg = total / runningQty

            else:
                if entryQuantity > runningQty:
                    raise HTTPException(status_code=422, detail="sell exceeds holding")
                runningQty -= entryQuantity

        return runningQty, runningAvg

    @classmethod
    def recalcHolding(cls, db: Session, wallet: Wallet, ticker: str) -> Holding | None:
        walletId = int(wallet.walletId)
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

        quantity, avg = cls.applyEntries(Decimal(0), Decimal(0), entries)
        if holding is None:
            xangoDefault = PositionsManager.fetchXangoScores((ticker,)).get(ticker)
            holding = Holding(
                walletId=walletId,
                assetType=entries[0].assetType,
                ticker=ticker,
                quantity=quantity,
                avgPrice=avg,
                rating=xangoDefault if xangoDefault is not None else 10.0,  # type: ignore[assignment]
            )

            db.add(holding)
        else:
            holding.quantity = quantity  # type: ignore[assignment]
            holding.avgPrice = avg  # type: ignore[assignment]
            holding.assetType = entries[0].assetType  # type: ignore[assignment]

        return holding

    @classmethod
    def addEntry(cls, db: Session, wallet: Wallet, data: EntryCreate) -> tuple[Transaction, Holding | None]:
        walletId = int(wallet.walletId)
        if data.asset_type not in ALLOWED_ASSET_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"unknown asset_type '{data.asset_type}', expected one of: {', '.join(sorted(ALLOWED_ASSET_TYPES))}",
            )
        if data.side == "Venda":
            holding = db.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == data.ticker).first()
            if holding is None or toDecimal(data.quantity) > toDecimal(holding.quantity):
                raise HTTPException(status_code=422, detail="sell exceeds holding")

        entry = Transaction(
            walletId=walletId,
            side=data.side,
            assetType=data.asset_type,
            ticker=data.ticker,
            date=data.date,
            quantity=toDecimal(data.quantity),
            price=toDecimal(data.price),
            costs=toDecimal(data.costs),
        )

        db.add(entry)
        db.flush()

        holding = cls.recalcHolding(db, wallet, data.ticker)

        db.commit()
        db.refresh(entry)

        if holding is not None:
            db.refresh(holding)

        return entry, holding

    @classmethod
    def listEntries(
        cls, db: Session, wallet: Wallet, ticker: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[int, list[Transaction]]:
        walletId = int(wallet.walletId)
        query = db.query(Transaction).filter(Transaction.walletId == walletId)

        if ticker is not None:
            query = query.filter(Transaction.ticker == ticker)

        total = query.count()
        items = query.order_by(Transaction.date, Transaction.entryId).offset(offset).limit(limit).all()

        return total, items

    @classmethod
    def updateEntry(
        cls, db: Session, wallet: Wallet, entryId: int, patch: EntryUpdate
    ) -> tuple[Transaction, Holding | None]:
        entry = db.query(Transaction).filter(Transaction.entryId == entryId).first()

        if entry is None:
            raise HTTPException(status_code=404, detail="entry not found")

        if int(entry.walletId) != int(wallet.walletId):
            raise HTTPException(status_code=404, detail="entry not found")

        changes = patch.model_dump(exclude_unset=True)
        if changes.get("asset_type") is not None and changes["asset_type"] not in ALLOWED_ASSET_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"unknown asset_type '{changes['asset_type']}', expected one of: {', '.join(sorted(ALLOWED_ASSET_TYPES))}",
            )
        if "asset_type" in changes:
            entry.assetType = changes.pop("asset_type")  # type: ignore[assignment]
        for fieldName, fieldValue in changes.items():
            if fieldValue is not None:
                if fieldName in NUMERIC_PATCH_FIELDS:
                    fieldValue = toDecimal(fieldValue)
                setattr(entry, fieldName, fieldValue)

        db.flush()

        try:
            holding = cls.recalcHolding(db, wallet, str(entry.ticker))
        except HTTPException:
            db.rollback()
            raise

        db.commit()
        db.refresh(entry)

        if holding is not None:
            db.refresh(holding)

        return entry, holding

    @classmethod
    def deleteEntry(cls, db: Session, wallet: Wallet, entryId: int) -> tuple[int, Holding | None]:
        entry = db.query(Transaction).filter(Transaction.entryId == entryId).first()

        if entry is None:
            raise HTTPException(status_code=404, detail="entry not found")

        if int(entry.walletId) != int(wallet.walletId):
            raise HTTPException(status_code=404, detail="entry not found")

        ticker = entry.ticker

        db.delete(entry)
        db.flush()

        try:
            holding = cls.recalcHolding(db, wallet, str(ticker))
        except HTTPException:
            db.rollback()
            raise

        db.commit()

        return entryId, holding
