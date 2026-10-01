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


async def wallet_positions(wallet_id: int, **_) -> dict:
    """List wallet holdings with live prices, equity, allocation, and buy signals.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        return PositionsManager.getPositions(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_summary(wallet_id: int, **_) -> dict:
    """Summarize applied capital, equity, and variation for a wallet.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to summarize (must belong to the caller)
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        return SummaryManager.getSummary(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_allocation(wallet_id: int, group_by: str = "ticker", **_) -> dict:
    """Break wallet equity down by ticker or asset type.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        group_by: Grouping key — "ticker" or "assetType" (default "ticker")
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        return SummaryManager.getAllocation(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            group_by,
        )
    finally:
        closeOwnSession(db, ownSession)


async def list_wallet_earnings(wallet_id: int, status: Optional[str] = "A Receber", **_) -> dict:
    """List accrued earnings (dividends, JSCP) for a wallet.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        status: Filter by status — "A Receber", "Recebido", or None for all (default "A Receber")
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        rows = EarningsManager.listEarnings(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            status=status,
        )
        return {
            "wallet_id": wallet_id,
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


async def wallet_performance(
    wallet_id: int, from_date: str, to_date: str, ticker: Optional[str] = None, **_
) -> dict:
    """Compute time-weighted return, volatility, and dividends for a wallet or ticker.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        from_date: Window start as YYYY-MM-DD
        to_date: Window end as YYYY-MM-DD
        ticker: Optional single ticker; omit for the whole wallet
    """
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
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        return PerformanceManager.getPerformance(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            ticker,
            startDate,
            endDate,
        )
    finally:
        closeOwnSession(db, ownSession)


async def wallet_rebalance(wallet_id: int, **_) -> dict:
    """Show weight-share rebalance deltas per ticker (buy/sell/hold).

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        userId = user["userId"]
        ownerError = ensureOwnership(db, wallet_id, userId)
        if ownerError is not None:
            return ownerError
        return PositionsManager.getRebalance(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        closeOwnSession(db, ownSession)
