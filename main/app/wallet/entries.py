import logging
from datetime import date as dateType
from typing import Literal, get_args

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from main.app.wallet.positions import PositionsManager
from main.models.wallet import Holding, Transaction, Wallet

logger = logging.getLogger(__name__)

AssetType = Literal["ACOES", "OUTROS"]
ALLOWED_ASSET_TYPES = frozenset(get_args(AssetType))


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
    def applyEntries(cls, quantity: float, avg: float, entries: list[Transaction]) -> tuple[float, float]:
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

        quantity, avg = cls.applyEntries(0.0, 0.0, entries)
        if holding is None:
            xangoScore = PositionsManager.fetchXangoScores((ticker,)).get(ticker)
            holding = Holding(
                walletId=walletId,
                assetType=entries[0].assetType,
                ticker=ticker,
                quantity=quantity,
                avgPrice=avg,
                rating=xangoScore if xangoScore is not None else 10.0,  # type: ignore[assignment]
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
            if holding is None or data.quantity > float(holding.quantity):
                raise HTTPException(status_code=422, detail="sell exceeds holding")

        entry = Transaction(
            walletId=walletId,
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

    @classmethod
    def positionAtDate(cls, entries: list[Transaction], exDate: dateType) -> float:
        datedEntries = [entry for entry in entries if str(entry.date) <= exDate.isoformat()]
        quantity, _ = cls.applyEntries(0.0, 0.0, datedEntries)

        return quantity
