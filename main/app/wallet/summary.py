import logging
from datetime import date as dateType
from datetime import datetime, timedelta
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Holding, Snapshot, Target, Transaction

logger = logging.getLogger(__name__)


class TargetUpsert(BaseModel):
    wallet_id: int
    key_kind: Literal["ticker", "group"]
    key_value: str
    percent_ideal: float = Field(ge=0, le=100)


class RatingUpsert(BaseModel):
    wallet_id: int
    ticker: str
    rating: float = Field(ge=0, le=100)


class SummaryManager:
    @classmethod
    def twrOrNone(cls, db: Session, walletId: int, userId: int, start: dateType, end: dateType) -> float | None:
        # Sync-on-read TWR for one window: TTL-cached via getPerformance, never
        # raises, None when unmeasurable (no market closes in window).
        try:
            startIso, endIso = start.isoformat(), end.isoformat()
            tickers = [
                str(row[0])
                for row in db.query(Transaction.ticker).filter(Transaction.walletId == walletId).distinct().all()
            ]
            for ticker in tickers:
                for closeDay, _ in PositionsManager.fetchPadraoCloses(ticker):
                    if startIso <= closeDay.isoformat() <= endIso:
                        return PerformanceManager.getPerformance(db, walletId, userId, None, start, end).get("twr")
            return None
        except Exception:
            logger.warning("auto-TWR failed for wallet %s", walletId, exc_info=True)
            return None

    @classmethod
    def autoTwr(cls, db: Session, walletId: int, userId: int) -> tuple[float | None, float | None]:
        # Lifetime + trailing-12m TWR computed at load time; (None, None) when empty.
        try:
            firstRow = (
                db.query(Transaction.date).filter(Transaction.walletId == walletId).order_by(Transaction.date).first()
            )
            if firstRow is None:
                return None, None
            today = dateType.today()
            yearAgo = today - timedelta(days=365)
            return (
                cls.twrOrNone(db, walletId, userId, firstRow[0], today),
                cls.twrOrNone(db, walletId, userId, max(firstRow[0], yearAgo), today),
            )
        except Exception:
            logger.warning("auto-TWR failed for wallet %s", walletId, exc_info=True)
            return None, None

    @classmethod
    def getSummary(cls, db: Session, walletId: int, userId: int) -> dict:
        wallet = WalletsManager.getWallet(db, walletId, userId)
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

        today = dateType.today()

        profitTwr, profitTwr12m = cls.autoTwr(db, walletId, userId)

        snapshot = db.query(Snapshot).filter(Snapshot.walletId == walletId, Snapshot.date == today).first()
        if snapshot is None:
            snapshot = Snapshot(
                walletId=walletId,
                date=today,
                applied=applied,
                equity=equity,
                variation=variation,
                profitTwr=profitTwr,
                profitAmount=variation,
                profitTwr12m=profitTwr12m,
                profitTwr12mAmount=variation,
            )
            db.add(snapshot)
        else:
            snapshot.applied = applied  # type: ignore[assignment]
            snapshot.equity = equity  # type: ignore[assignment]
            snapshot.variation = variation  # type: ignore[assignment]
            snapshot.profitTwr = profitTwr  # type: ignore[assignment]
            snapshot.profitAmount = variation  # type: ignore[assignment]
            snapshot.profitTwr12m = profitTwr12m  # type: ignore[assignment]
            snapshot.profitTwr12mAmount = variation  # type: ignore[assignment]

        wallet.lastRecalc = datetime.now()

        db.commit()

        return {
            "applied": applied,
            "equity": equity,
            "variation": variation,
            "profit_twr": profitTwr,
            "profit_amount": variation,
            "profit_twr_12m": profitTwr12m,
            "profit_twr_12m_amount": variation,
        }

    @classmethod
    def getAllocation(cls, db: Session, walletId: int, userId: int, groupBy: str) -> dict:
        WalletsManager.getWallet(db, walletId, userId)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

        tickers = sorted({str(holding.ticker) for holding in holdings})
        prices = PositionsManager.fetchLivePrices(tickers)
        PositionsManager.fillMissingCloses(prices)

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

    @classmethod
    def upsertTarget(cls, db: Session, userId: int, data: TargetUpsert) -> Target:
        WalletsManager.getWallet(db, data.wallet_id, userId)
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

    @classmethod
    def set_rating(cls, db: Session, userId: int, data: RatingUpsert) -> Holding:
        WalletsManager.getWallet(db, data.wallet_id, userId)
        holding = db.query(Holding).filter(Holding.walletId == data.wallet_id, Holding.ticker == data.ticker).first()

        if holding is None:
            raise HTTPException(status_code=404, detail="holding not found")

        holding.rating = data.rating  # type: ignore[assignment]

        db.commit()
        db.refresh(holding)

        return holding


set_rating = SummaryManager.set_rating
