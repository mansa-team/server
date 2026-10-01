import logging
from datetime import date as dateType

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal

from config import getSession
from main.app.wallet import summary  # pinned: set_rating_route handler calls summary.set_rating (digest test)
from main.app.wallet.earnings import EarningsManager
from main.app.wallet.entries import EntriesManager, EntryCreate, EntryUpdate
from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.summary import RatingUpsert, SummaryManager, TargetUpsert
from main.app.wallet.wallets import WalletsManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])


class WalletCreate(BaseModel):
    name: str


@router.post("/wallets", response_class=ORJSONResponse, status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    userId: int,
    db: Session = Depends(getSession),
):
    wallet = WalletsManager.createWallet(db, userId, payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets", response_class=ORJSONResponse)
def list_wallets_route(
    userId: int,
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in WalletsManager.listWallets(db, userId)
    ]


def serialize_holding(holding) -> dict | None:
    if holding is None:
        return None
    return {"ticker": holding.ticker, "quantity": float(holding.quantity), "avgPrice": float(holding.avgPrice)}


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


@router.post("/entries", response_class=ORJSONResponse, status_code=201)
def create_entry_route(
    payload: EntryCreate,
    userId: int,
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.addEntry(db, userId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.get("/entries", response_class=ORJSONResponse)
def list_entries_route(
    wallet_id: int,
    ticker: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    userId: int = Query(),
    db: Session = Depends(getSession),
):
    total, items = EntriesManager.listEntries(db, userId, wallet_id, ticker, limit, offset)
    return {"total": total, "items": [serialize_entry(item) for item in items]}


@router.patch("/entries/{entryId}", response_class=ORJSONResponse)
def update_entry_route(
    entryId: int,
    payload: EntryUpdate,
    userId: int,
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.updateEntry(db, userId, entryId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.delete("/entries/{entryId}", response_class=ORJSONResponse)
def delete_entry_route(
    entryId: int,
    userId: int,
    db: Session = Depends(getSession),
):
    deletedId, holding = EntriesManager.deleteEntry(db, userId, entryId)
    return {"entryId": deletedId, "holding": serialize_holding(holding)}


@router.get("/positions", response_class=ORJSONResponse)
def list_positions_route(
    wallet_id: int,
    userId: int,
    db: Session = Depends(getSession),
):
    return PositionsManager.getPositions(db, wallet_id, userId)


@router.get("/rebalance", response_class=ORJSONResponse)
def get_rebalance_route(
    wallet_id: int,
    userId: int,
    db: Session = Depends(getSession),
):
    return PositionsManager.getRebalance(db, wallet_id, userId)


@router.get("/summary", response_class=ORJSONResponse)
def get_summary_route(
    wallet_id: int,
    userId: int,
    db: Session = Depends(getSession),
):
    return SummaryManager.getSummary(db, wallet_id, userId)


@router.get("/allocation", response_class=ORJSONResponse)
def get_allocation_route(
    wallet_id: int,
    group_by: Literal["ticker", "type"] = Query(default="ticker"),
    userId: int = Query(),
    db: Session = Depends(getSession),
):
    return SummaryManager.getAllocation(db, wallet_id, userId, group_by)


@router.put("/targets", response_class=ORJSONResponse)
def upsert_target_route(
    payload: TargetUpsert,
    userId: int,
    db: Session = Depends(getSession),
):
    target = SummaryManager.upsertTarget(db, userId, payload)
    return {
        "wallet_id": target.walletId,
        "key_kind": target.keyKind,
        "key_value": target.keyValue,
        "percent_ideal": float(target.percentIdeal),
    }


@router.put("/ratings", response_class=ORJSONResponse)
def set_rating_route(
    payload: RatingUpsert,
    userId: int,
    db: Session = Depends(getSession),
):
    holding = summary.set_rating(db, userId, payload)
    return {"ticker": holding.ticker, "rating": holding.rating}


class EarningsSync(BaseModel):
    wallet_id: int


def serialize_earning(earning) -> dict:
    return {
        "ticker": earning.ticker,
        "kind": earning.kind,
        "gross": float(earning.gross),
        "net_ir_adjusted": float(earning.netIrAdjusted),
        "status": earning.status,
    }


@router.get("/earnings", response_class=ORJSONResponse)
def list_earnings_route(
    wallet_id: int,
    status: str | None = None,
    userId: int = Query(),
    db: Session = Depends(getSession),
):
    return {"items": [serialize_earning(item) for item in EarningsManager.listEarnings(db, wallet_id, userId, status)]}


@router.post("/earnings/sync", response_class=ORJSONResponse)
def sync_earnings_route(
    payload: EarningsSync,
    userId: int,
    db: Session = Depends(getSession),
):
    return EarningsManager.syncEarnings(db, payload.wallet_id, userId)


@router.get("/performance", response_class=ORJSONResponse)
def get_performance_route(
    wallet_id: int,
    ticker: str | None = None,
    fromIso: str = Query(alias="from"),
    toIso: str = Query(alias="to"),
    userId: int = Query(),
    db: Session = Depends(getSession),
):
    try:
        startDate = dateType.fromisoformat(fromIso)
        endDate = dateType.fromisoformat(toIso)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date, expected YYYY-MM-DD")
    return PerformanceManager.getPerformance(db, wallet_id, userId, ticker, startDate, endDate)
