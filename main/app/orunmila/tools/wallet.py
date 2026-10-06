from datetime import date as dateType
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.app.orunmila.tools.context import closeOwnSession, popAuthSession
from main.app.wallet.earnings import EarningsManager
from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.summary import SummaryManager
from main.app.wallet.wallets import WalletsManager


def ensureOwnership(db: Session | None, walletId: int, userId: int) -> dict | None:
    try:
        WalletsManager.getWallet(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
    except HTTPException:
        return {"error": "not-owner"}
    return None


def resolveWalletId(db: Session | None, userId: int) -> int:
    """Server-side wallet resolution: the wallet id never comes from the LLM."""
    wallet = WalletsManager.getMyWallet(db, userId)  # type: ignore[arg-type]
    return int(wallet.walletId)


async def wallet_positions(**_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        return PositionsManager.getPositions(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_summary(**_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        return SummaryManager.getSummary(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_allocation(group_by: str = "ticker", **_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        body = SummaryManager.getAllocation(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
        # Grouping + pct are client-side (same as the HTTP endpoint).
        groupEquity: dict[str, float] = {}
        for item in body["items"]:
            groupKey = item["ticker"] if group_by == "ticker" else item["asset_type"]
            groupEquity[groupKey] = groupEquity.get(groupKey, 0.0) + item["equity"]
        equityTotal = body["equity_total"]
        return {
            "items": [
                {"key": groupKey, "equity": groupValue, "pct": (groupValue / equityTotal) if equityTotal else 0}
                for groupKey, groupValue in groupEquity.items()
            ],
            "equity_total": equityTotal,
        }
    finally:
        closeOwnSession(db, ownSession)


async def list_wallet_earnings(status: Optional[str] = "A Receber", **_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        rows = EarningsManager.listEarnings(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
        if status is not None:
            rows = [row for row in rows if str(row.status) == status]
        return {
            "wallet_id": walletId,
            "status": status,
            "earnings": [
                {
                    "earning_id": int(row.earningId),
                    "ticker": str(row.ticker),
                    "kind": str(row.kind),
                    "ex_date": str(row.exDate),
                    "pay_date": str(row.payDate),
                    "gross": float(row.gross),
                    "net": float(row.netIrAdjusted),
                    "status": str(row.status),
                }
                for row in rows
            ],
        }
    finally:
        closeOwnSession(db, ownSession)


async def wallet_performance(from_date: str, to_date: str, ticker: Optional[str] = None, **_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        try:
            startDate = dateType.fromisoformat(from_date)
            endDate = dateType.fromisoformat(to_date)
        except ValueError:
            return {"error": "invalid date, use YYYY-MM-DD"}

        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        return PerformanceManager.getPerformance(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
            ticker,
            startDate,
            endDate,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_rebalance(**_) -> dict:
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        walletId = resolveWalletId(db, userId)
        ownerError = ensureOwnership(db, walletId, userId)
        if ownerError is not None:
            return ownerError
        return PositionsManager.getRebalance(
            db,  # type: ignore[arg-type]
            walletId,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)
