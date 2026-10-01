import logging

from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Literal

from config import getSession
from main.app.wallet.auth import requireWalletUser
from main.service import wallet_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])


class WalletCreate(BaseModel):
    name: str


@router.post("/wallets", response_class=ORJSONResponse, status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    wallet = wallet_service.create_wallet(db, user["userId"], payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets", response_class=ORJSONResponse)
def list_wallets_route(
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in wallet_service.list_wallets(db, user["userId"])
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
    payload: wallet_service.EntryCreate,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    entry, holding = wallet_service.add_entry(db, user["userId"], payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.get("/entries", response_class=ORJSONResponse)
def list_entries_route(
    wallet_id: int,
    ticker: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    total, items = wallet_service.list_entries(db, user["userId"], wallet_id, ticker, limit, offset)
    return {"total": total, "items": [serialize_entry(item) for item in items]}


@router.patch("/entries/{entryId}", response_class=ORJSONResponse)
def update_entry_route(
    entryId: int,
    payload: wallet_service.EntryUpdate,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    entry, holding = wallet_service.update_entry(db, user["userId"], entryId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.delete("/entries/{entryId}", response_class=ORJSONResponse)
def delete_entry_route(
    entryId: int,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    deletedId, holding = wallet_service.delete_entry(db, user["userId"], entryId)
    return {"entryId": deletedId, "holding": serialize_holding(holding)}


@router.get("/positions", response_class=ORJSONResponse)
def list_positions_route(
    wallet_id: int,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return wallet_service.get_positions(db, wallet_id, user["userId"])


@router.get("/summary", response_class=ORJSONResponse)
def get_summary_route(
    wallet_id: int,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return wallet_service.get_summary(db, wallet_id, user["userId"])


@router.get("/allocation", response_class=ORJSONResponse)
def get_allocation_route(
    wallet_id: int,
    group_by: Literal["ticker", "type"] = Query(default="ticker"),
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return wallet_service.get_allocation(db, wallet_id, user["userId"], group_by)


@router.put("/targets", response_class=ORJSONResponse)
def upsert_target_route(
    payload: wallet_service.TargetUpsert,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    target = wallet_service.upsert_target(db, user["userId"], payload)
    return {
        "wallet_id": target.walletId,
        "key_kind": target.keyKind,
        "key_value": target.keyValue,
        "percent_ideal": float(target.percentIdeal),
    }


@router.put("/ratings", response_class=ORJSONResponse)
def set_rating_route(
    payload: wallet_service.RatingUpsert,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    holding = wallet_service.set_rating(db, user["userId"], payload)
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
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return {
        "items": [
            serialize_earning(item) for item in wallet_service.list_earnings(db, wallet_id, user["userId"], status)
        ]
    }


@router.post("/earnings/sync", response_class=ORJSONResponse)
def sync_earnings_route(
    payload: EarningsSync,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return wallet_service.sync_earnings(db, payload.wallet_id, user["userId"])
