from datetime import date as dateType
from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from main.app.wallet.entries import EntriesManager
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Holding, Snapshot, Transaction, Wallet


class RatingUpsert(BaseModel):
    ticker: str
    rating: float = Field(ge=0, le=100)


class SummaryManager:
    @classmethod
    def ledgerPositions(cls, db: Session, wallet: Wallet) -> dict[str, dict]:
        walletId = int(wallet.walletId)
        rows = (
            db.query(Transaction)
            .filter(Transaction.walletId == walletId)
            .order_by(Transaction.date, Transaction.entryId)
            .all()
        )
        byTicker: dict[str, list] = {}
        for row in rows:
            byTicker.setdefault(str(row.ticker), []).append(row)

        positions: dict[str, dict] = {}
        for ticker, tickerRows in byTicker.items():
            try:
                quantity, avg = EntriesManager.applyEntries(0.0, 0.0, tickerRows)
            except HTTPException:
                quantity, avg = Decimal(0), Decimal(0)
            if quantity > 0:
                positions[ticker] = {
                    "quantity": quantity,
                    "avgPrice": avg,
                    "assetType": str(tickerRows[0].assetType),
                }
        return positions

    @classmethod
    def getSummary(cls, db: Session, wallet: Wallet) -> dict:
        walletId = int(wallet.walletId)
        _, prices, _, _ = PositionsManager.pricePass(db, wallet)
        positions = cls.ledgerPositions(db, wallet)
        applied = sum((item["quantity"] * item["avgPrice"] for item in positions.values()), Decimal(0))

        equity: Decimal = Decimal(0)
        for ticker, item in positions.items():
            price = prices.get(ticker)
            if price is not None:
                equity += item["quantity"] * price
        variation = equity - applied

        firstRow = (
            db.query(Transaction.date).filter(Transaction.walletId == walletId).order_by(Transaction.date).first()
        )
        firstDate = firstRow[0].isoformat() if firstRow else None

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

        db.commit()

        return {
            "applied": float(applied),
            "equity": float(equity),
            "variation": float(variation),
            "first_date": firstDate,
        }

    @classmethod
    def getAllocation(cls, db: Session, wallet: Wallet) -> dict:
        _, prices, _, _ = PositionsManager.pricePass(db, wallet)
        positions = cls.ledgerPositions(db, wallet)

        items: list[dict] = []
        for ticker, item in positions.items():
            price = prices.get(ticker)
            holdingEquity = float(item["quantity"] * price) if price is not None else 0.0
            items.append(
                {
                    "ticker": ticker,
                    "asset_type": item["assetType"],
                    "equity": holdingEquity,
                }
            )

        equityTotal = sum(item["equity"] for item in items)

        return {"items": items, "equity_total": equityTotal}

    @classmethod
    def set_rating(cls, db: Session, wallet: Wallet, data: RatingUpsert) -> Holding:
        walletId = int(wallet.walletId)
        holding = db.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == data.ticker).first()

        if holding is None:
            raise HTTPException(status_code=404, detail="holding not found")

        holding.rating = data.rating  # type: ignore[assignment]

        db.commit()
        db.refresh(holding)

        return holding
