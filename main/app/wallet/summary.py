from datetime import date as dateType
from datetime import datetime

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from main.app.wallet.positions import PositionsManager
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Holding, Snapshot, Transaction


class RatingUpsert(BaseModel):
    ticker: str
    rating: float = Field(ge=0, le=100)


class SummaryManager:
    @classmethod
    def getSummary(cls, db: Session, walletId: int, userId: int) -> dict:
        # Canonical raw: applied/equity/variation + firstDate. TWR presets are
        # client-side (GET /wallet/performance?from&to); no auto-TWR here.
        wallet = WalletsManager.getWallet(db, walletId, userId)
        PositionsManager.maybeRefreshRatings(db, walletId)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
        applied = sum(float(holding.quantity) * float(holding.avgPrice) for holding in holdings)
        tickers = sorted({str(holding.ticker) for holding in holdings})
        prices = PositionsManager.fetchLivePrices(tickers)
        PositionsManager.fillMissingCloses(prices)

        equity = 0.0
        for holding in holdings:
            price = prices.get(str(holding.ticker))
            if price is not None:
                equity += float(holding.quantity) * price
        variation = equity - applied

        firstRow = (
            db.query(Transaction.date).filter(Transaction.walletId == walletId).order_by(Transaction.date).first()
        )
        firstDate = firstRow[0].isoformat() if firstRow else None

        today = dateType.today()

        # Snapshot keeps applied/equity/variation history; TWR columns stay NULL
        # (client resolves TWRs, so server-computed snapshot TWRs would go stale).
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
            "first_date": firstDate,
        }

    @classmethod
    def getAllocation(cls, db: Session, walletId: int, userId: int) -> dict:
        # Canonical raw: per-holding equities + total. Grouping + pct are client-side.
        WalletsManager.getWallet(db, walletId, userId)
        PositionsManager.maybeRefreshRatings(db, walletId)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

        tickers = sorted({str(holding.ticker) for holding in holdings})
        prices = PositionsManager.fetchLivePrices(tickers)
        PositionsManager.fillMissingCloses(prices)

        items = []
        for holding in holdings:
            price = prices.get(str(holding.ticker))
            holdingEquity = float(holding.quantity) * price if price is not None else 0.0
            items.append(
                {
                    "ticker": str(holding.ticker),
                    "asset_type": str(holding.assetType),
                    "equity": holdingEquity,
                }
            )

        equityTotal = sum(item["equity"] for item in items)

        return {"items": items, "equity_total": equityTotal}

    @classmethod
    def set_rating(cls, db: Session, userId: int, walletId: int, data: RatingUpsert) -> Holding:
        WalletsManager.getWallet(db, walletId, userId)
        holding = db.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == data.ticker).first()

        if holding is None:
            raise HTTPException(status_code=404, detail="holding not found")

        holding.rating = data.rating  # type: ignore[assignment]

        db.commit()
        db.refresh(holding)

        return holding


set_rating = SummaryManager.set_rating
