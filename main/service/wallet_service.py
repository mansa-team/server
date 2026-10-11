"""Wallet service: HTTP routes plus the wallet MCP server.

The MCP surface is eleven hand-written tools delegating to route functions:
seven read routes plus four LLM-shaped wrappers. Ledger writes stay off MCP
unless wrapped, and wallet creation/lookup is always server-side. Wallet
responses have no compact form: plain HTTP and MCP serve the same JSON.
"""

import logging
from typing import Annotated, Literal

from fastapi import HTTPException
from fastmcp import FastMCP
from pydantic import Field
from sqlalchemy.orm import Session

from config import SessionLocal
from main.app.authentication.session import SessionManager
from main.app.authentication.util import verifyAccessToken, walletAuth
from main.app.wallet.entries import AssetType
from main.controller.wallet_controller import (
    router as walletRouter,
    explain_twr_route,
    get_allocation_route,
    get_performance_route,
    get_progression_route,
    get_rebalance_route,
    get_summary_route,
    list_earnings_route,
    list_positions_route,
    record_entry_route,
    set_rating_wrapper_route,
    wallet_progression_route,
)
from main.utils.service_manager import getApp

logger = logging.getLogger(__name__)


class WalletService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(walletRouter)

        walletMcp = buildWalletMCP()
        mcpApp = walletMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/wallet/mcp", mcpApp)
        # Mounted sub-app lifespans never run under uvicorn: adopt it so the
        # streamable session manager is initialized for POST traffic.
        service.router.lifespan_context = mcpApp.lifespan


def resolveMcpIdentity(authorization: str, db: Session) -> dict:
    """Session JWT from an MCP tool arg -> verified claims with revocation check.

    Raises HTTPException 401 on missing, expired, forged, or revoked sessions.
    """
    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    currentUser = verifyAccessToken(token)
    userIdRaw = currentUser.get("userId")
    if userIdRaw is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    try:
        userId = int(userIdRaw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")
    sessionId = currentUser.get("sessionId")
    if not sessionId or not SessionManager.validateSession(db, str(sessionId), userId):
        raise HTTPException(status_code=401, detail="Session revoked")
    return currentUser


def buildWalletMCP() -> FastMCP:
    """Hand-written wallet MCP server: 11 thin tools delegating to route functions."""
    mcp = FastMCP("Mansa Wallet MCP", auth=walletAuth)

    @mcp.tool
    def wallet_positions(authorization: str = "") -> dict:
        """Get the wallet's current positions with cost basis, market prices and equity.

        PARAMETERS:
        - None: the wallet is resolved server-side from the session user.

        RESPONSE format:
        {"items": [{"ticker": "PETR4", "quantity": 10.0, "avgPrice": 25.1,
        "current_price": 28.4, "equity": 284.0, "rating": 72.0,
        "percent_ideal": null}], "equity_total": 284.0}

        WORKFLOW:
        1. Call this first to see what the user holds and each position's equity
        2. `rating` (0-100) is the single wallet rating: Xango default, user-overridable
        3. Drill into one ticker with wallet_performance or explain_twr

        EXAMPLES:
        - "What stocks do I own?" → call wallet_positions with no arguments
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return list_positions_route(currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_rebalance(authorization: str = "") -> dict:
        """Get the target-weight snapshot used for rebalancing advice.

        PARAMETERS:
        - None.

        RESPONSE format:
        {"items": [{"ticker": "PETR4", "weight": 72.0, "current_price": 28.4,
        "equity": 284.0}], "equity_total": 284.0}

        WORKFLOW:
        1. `weight` mirrors the single rating (0-100); percentages/deltas are
           agent-side arithmetic over this snapshot
        2. Combine with wallet_positions to compare current vs target exposure

        EXAMPLES:
        - "Am I overweight anywhere?" → wallet_rebalance + wallet_positions
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return get_rebalance_route(currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_summary(authorization: str = "") -> dict:
        """Get the ledger-derived wallet summary (applied capital, equity, variation).

        PARAMETERS:
        - None.

        RESPONSE format:
        {"applied": 1000.0, "equity": 1120.5, "variation": 120.5,
        "first_date": "2026-01-05"}

        WORKFLOW:
        1. Use for totals: how much was put in, what it is worth now, the delta
        2. For returns over time prefer explain_twr or wallet_performance

        EXAMPLES:
        - "How much have I made overall?" → wallet_summary
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return get_summary_route(currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_allocation(authorization: str = "") -> dict:
        """Get per-position equity lines to group by ticker or asset type.

        PARAMETERS:
        - None. Grouping and percentages are agent-side arithmetic.

        RESPONSE format:
        {"items": [{"ticker": "PETR4", "asset_type": "ACOES", "equity": 284.0}],
        "equity_total": 284.0}

        WORKFLOW:
        1. Map the user's grouping request (ticker/asset_type) onto these lines
        2. pct = equity / equity_total; ACOES vs OUTROS split is the common ask

        EXAMPLES:
        - "How much of my wallet is in stocks vs other assets?" → wallet_allocation
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return get_allocation_route(currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_earnings(authorization: str = "") -> dict:
        """List wallet earnings (dividends/JCP/rents) with status and net values.

        PARAMETERS:
        - None. Filtering by status/ticker is agent-side over the returned items.

        RESPONSE format:
        {"items": [{"ticker": "PETR4", "kind": "DIVIDENDO", "gross": 12.5,
        "net_ir_adjusted": 12.5, "status": "A Receber"}]}

        WORKFLOW:
        1. Use for "what am I receiving / received" questions
        2. TWR already folds dividends via explain_twr's dividend leg

        EXAMPLES:
        - "Which dividends are still to be paid?" → wallet_earnings, filter status
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return list_earnings_route(currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_performance(
        ticker: str | None = None,
        fromIso: str | None = None,
        toIso: str | None = None,
        authorization: str = "",
    ) -> dict:
        """Get time-weighted performance metrics (TWR, volatility, dividends) for a window.

        PARAMETERS:
        - `ticker` (optional): Restrict to one ticker; omit for the whole wallet.
        - `fromIso` (optional): ISO start date ("YYYY-MM-DD"); omit for first ledger date.
        - `toIso` (optional): ISO end date; omit for today.

        RESPONSE format:
        {"twr": 0.112, "twr_annualized": 0.28, "volatility": 0.2,
        "dividends_received": 34.2, "price_return": 0.09}

        WORKFLOW:
        1. For a plain metric read use this; for a ready-made explanation with
           per-ticker attribution use explain_twr instead
        2. External contributions are neutral by construction (TWR)

        EXAMPLES:
        - "My return since January?" → fromIso="2026-01-01"
        - "VALE3 return this year?" → ticker="VALE3", fromIso="2026-01-01"
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return get_performance_route(ticker=ticker, fromIso=fromIso, toIso=toIso, currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def wallet_progression_series(
        fromIso: str | None = None,
        toIso: str | None = None,
        authorization: str = "",
    ) -> dict:
        """Get the raw daily equity/invested progression series (up to ~2000 points).

        PARAMETERS:
        - `fromIso` (optional): ISO start date; omit for first ledger date.
        - `toIso` (optional): ISO end date; omit for today.

        RESPONSE format:
        {"granularity": "daily", "from": "...", "to": "...",
        "points": [{"date": "2026-01-05", "equity": 1000.0, "invested": 1000.0}]}

        WORKFLOW:
        1. Prefer wallet_progression (downsampled) for chat answers; use this only
           when the full daily granularity is explicitly needed

        EXAMPLES:
        - "Every single day of my equity this year" → from="2026-01-01"
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return get_progression_route(fromIso=fromIso, toIso=toIso, currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def record_entry(
        side: Literal["Compra", "Venda"],
        asset_type: AssetType,
        ticker: str,
        date: str,
        quantity: float,
        price: float,
        costs: float = 0.0,
        authorization: str = "",
    ) -> dict:
        """Record a buy or sell in the wallet ledger from chat (MCP write wrapper).

        PARAMETERS:
        - `side` (required): "Compra" (buy) or "Venda" (sell).
        - `asset_type` (required): "ACOES" (B3 stocks) or "OUTROS" (anything else).
        - `ticker` (required): Ticker symbol, e.g. "PETR4".
        - `date` (required): Trade date, ISO "YYYY-MM-DD".
        - `quantity` (required): Positive share quantity.
        - `price` (required): Per-share price, >= 0.
        - `costs` (optional): Fees/taxes in BRL, default 0.0.

        RESPONSE format:
        {"entryId": 12, "holding": {"ticker": "PETR4", "quantity": 10.0,
        "avgPrice": 25.1}}

        WORKFLOW:
        1. Confirm side/ticker/quantity/price/date with the user BEFORE writing;
           never invent values
        2. Call once per trade; on success re-read wallet_positions to confirm
        3. Selling the full quantity removes the holding

        EXAMPLES:
        - "Bought 100 PETR4 at 25.50" → side="Compra", asset_type="ACOES", ticker="PETR4", date="2026-10-10", quantity=100, price=25.5
        - "Sold 50 VALE3 at 61.20 with 5 in fees" → side="Venda", asset_type="ACOES", ticker="VALE3", date="2026-09-30", quantity=50, price=61.2, costs=5.0
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return record_entry_route(
                side=side,
                asset_type=asset_type,
                ticker=ticker,
                date=date,
                quantity=quantity,
                price=price,
                costs=costs,
                currentUser=currentUser,
                db=db,
            )
        finally:
            db.close()

    @mcp.tool
    def set_rating(ticker: str, rating: float, authorization: str = "") -> dict:
        """Set the user's rating (0-100) for a held ticker — single rating field.

        PARAMETERS:
        - `ticker` (required): Ticker of an existing holding.
        - `rating` (required): 0-100. The Xango score is the default; user-set
          values are never clobbered by a Xango refresh.

        RESPONSE format:
        {"ticker": "PETR4", "rating": 80.0}

        WORKFLOW:
        1. Use wallet_rebalance/wallet_positions to see current ratings
        2. Only set what the user explicitly stated; 404 if the ticker is not held

        EXAMPLES:
        - "Raise PETR4 to 80 in my wallet" → ticker="PETR4", rating=80
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return set_rating_wrapper_route(ticker=ticker, rating=rating, currentUser=currentUser, db=db)
        finally:
            db.close()

    @mcp.tool
    def explain_twr(
        ticker: str | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        authorization: str = "",
    ) -> dict:
        """Explain time-weighted return: overall metrics, per-ticker TWR, worst tickers, dividend leg.

        PARAMETERS:
        - `ticker` (optional): Restrict to one ticker; omit for the whole wallet.
        - `from_date` (optional): ISO start date; omit for first ledger date.
        - `to_date` (optional): ISO end date; omit for today.

        RESPONSE format:
        {"from": "...", "to": "...", "ticker": null, "twr": 0.112,
        "twr_annualized": 0.28, "volatility": 0.2, "dividends_received": 34.2,
        "price_return": 0.09, "dividend_leg": 0.022,
        "tickers": [{"ticker": "PETR4", "twr": 0.15}, ...],
        "worst_tickers": [{"ticker": "VALE3", "twr": -0.04}, ...],
        "gloss": "one-sentence summary"}

        WORKFLOW:
        1. Call with the user's window (no dates = lifetime)
        2. `dividend_leg` = twr - price_return: the dividend contribution to total
        3. `tickers` lists standalone per-ticker TWR (best first); `worst_tickers`
           the 3 lowest; contributions are not capital-weighted

        EXAMPLES:
        - "Why is my return negative this year?" → from_date="2026-01-01"
        - "How did PETR4 do vs my wallet?" → ticker="PETR4"
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return explain_twr_route(
                ticker=ticker, from_date=from_date, to_date=to_date, currentUser=currentUser, db=db
            )
        finally:
            db.close()

    @mcp.tool
    def wallet_progression(
        from_date: str | None = None,
        to_date: str | None = None,
        max_points: Annotated[int, Field(ge=2, le=2000)] = 120,
        authorization: str = "",
    ) -> dict:
        """Get a downsampled equity/invested progression for chart-style answers.

        PARAMETERS:
        - `from_date` (optional): ISO start date; omit for first ledger date.
        - `to_date` (optional): ISO end date; omit for today.
        - `max_points` (optional): Target point count, 2..2000, default 120.

        RESPONSE format:
        {"granularity": "daily", "from": "...", "to": "...", "count": 250,
        "returned": 84, "stride": 3,
        "points": [{"date": "2026-01-05", "equity": 1000.0, "invested": 1000.0}]}

        WORKFLOW:
        1. Prefer this over the raw /progression read for chat (never ship ~2000 points)
        2. stride>1: every nth day kept; first and last day always included
        3. Totals/deltas come from wallet_summary, not from this series

        EXAMPLES:
        - "Chart my equity since January" → from_date="2026-01-01"
        - "Quick coarse look" → max_points=24
        """
        db = SessionLocal()
        try:
            currentUser = resolveMcpIdentity(authorization, db)
            return wallet_progression_route(
                from_date=from_date, to_date=to_date, max_points=max_points, currentUser=currentUser, db=db
            )
        finally:
            db.close()

    return mcp
