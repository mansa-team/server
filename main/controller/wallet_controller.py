from datetime import date as dateType
from math import ceil
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from config import getSession
from main.app.wallet.auth import getWalletUser
from main.app.wallet.analytics import AnalyticsManager
from main.app.wallet.earnings import EarningsManager, serialize_earning
from main.app.wallet.entries import (
    AssetType,
    EntriesManager,
    EntryCreate,
    EntryUpdate,
    serialize_entry,
    serialize_holding,
)
from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.summary import RatingUpsert, SummaryManager
from main.app.wallet.wallets import Wallet, WalletCreate, WalletsManager
from main.models.wallet import Transaction

# MCP auth: the `authorization` header param on MCP-exposed routes is not used
# by the handler itself — it puts the header in the OpenAPI schema so FastApiMCP
# pops args["authorization"] (injected by the agent dispatcher, never the LLM)
# into the replayed in-process request, where getWalletUser verifies it via
# POST /auth/introspect.
router = APIRouter(prefix="/wallet", tags=["Wallet"], dependencies=[Depends(getWalletUser)])


def getMyWallet(
    db: Session = Depends(getSession),
    currentUser: dict = Depends(getWalletUser),
) -> Wallet:
    return WalletsManager.getMyWallet(db, int(currentUser["userId"]))


@router.post("/wallets", status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    currentUser: dict = Depends(getWalletUser),
    db: Session = Depends(getSession),
):
    wallet = WalletsManager.getMyWallet(db, int(currentUser["userId"]), payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets")
def list_wallets_route(
    currentUser: dict = Depends(getWalletUser),
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in WalletsManager.listWallets(db, int(currentUser["userId"]))
    ]


@router.post("/entries", status_code=201)
def create_entry_route(
    payload: EntryCreate,
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.addEntry(db, wallet, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.get("/entries")
def list_entries_route(
    ticker: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    total, items = EntriesManager.listEntries(db, wallet, ticker, limit, offset)
    return {"total": total, "items": [serialize_entry(item) for item in items]}


@router.patch("/entries/{entryId}")
def update_entry_route(
    entryId: int,
    payload: EntryUpdate,
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.updateEntry(db, wallet, entryId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.delete("/entries/{entryId}")
def delete_entry_route(
    entryId: int,
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    deletedId, holding = EntriesManager.deleteEntry(db, wallet, entryId)
    return {"entryId": deletedId, "holding": serialize_holding(holding)}


@router.get("/positions", operation_id="wallet_positions")
def list_positions_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    return PositionsManager.getPositions(db, wallet)


@router.get("/rebalance", operation_id="wallet_rebalance")
def get_rebalance_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    return PositionsManager.getRebalance(db, wallet)


@router.get("/summary", operation_id="wallet_summary")
def get_summary_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    return SummaryManager.getSummary(db, wallet)


@router.get("/allocation", operation_id="wallet_allocation")
def get_allocation_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    return SummaryManager.getAllocation(db, wallet)


@router.put("/ratings")
def set_rating_route(
    payload: RatingUpsert,
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    """Single-rating override: PUT sets `Holding.rating` (Xango default, user-overwritable)."""
    holding = SummaryManager.set_rating(db, wallet, payload)
    return {"ticker": holding.ticker, "rating": holding.rating}


@router.get("/earnings", operation_id="wallet_earnings")
def list_earnings_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    return {"items": [serialize_earning(item) for item in EarningsManager.listEarnings(db, wallet)]}


@router.get("/performance", operation_id="wallet_performance")
def get_performance_route(
    ticker: str | None = None,
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    - "My return since January?" → from="2026-01-01"
    - "VALE3 return this year?" → ticker="VALE3", from="2026-01-01"
    """
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return PerformanceManager.getPerformance(db, wallet, ticker, startDate, endDate)


@router.get("/progression", operation_id="wallet_progression_series")
def get_progression_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getProgression(db, wallet, startDate, endDate)


@router.post("/record-entry", operation_id="record_entry")
def record_entry_route(
    side: Literal["Compra", "Venda"] = Body(...),
    asset_type: AssetType = Body(...),
    ticker: str = Body(...),
    date: str = Body(...),
    quantity: float = Body(..., gt=0),
    price: float = Body(..., ge=0),
    costs: float = Body(default=0.0, ge=0),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    - "Bought 100 PETR4 at 25.50 today" → side="Compra", asset_type="ACOES",
      ticker="PETR4", date=<today ISO>, quantity=100, price=25.5
    - "Sold 50 VALE3 at 61.20 on 2026-09-30, 5 in fees" → side="Venda",
      asset_type="ACOES", ticker="VALE3", date="2026-09-30", quantity=50,
      price=61.2, costs=5.0
    """
    try:
        parsedDate = dateType.fromisoformat(date)
    except ValueError:
        raise HTTPException(status_code=422, detail="invalid date, expected YYYY-MM-DD")

    entry, holding = EntriesManager.addEntry(
        db,
        wallet,
        EntryCreate(
            side=side,
            asset_type=asset_type,
            ticker=ticker,
            date=parsedDate,
            quantity=quantity,
            price=price,
            costs=costs,
        ),
    )
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.put("/set-rating", operation_id="set_rating")
def set_rating_wrapper_route(
    ticker: str = Body(...),
    rating: float = Body(..., ge=0, le=100),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    holding = SummaryManager.set_rating(db, wallet, RatingUpsert(ticker=ticker, rating=rating))
    return {"ticker": holding.ticker, "rating": holding.rating}


@router.get("/explain-twr", operation_id="explain_twr")
def explain_twr_route(
    ticker: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, from_date, to_date)
    overall = PerformanceManager.getPerformance(db, wallet, ticker, startDate, endDate)

    if ticker:
        tickerRows: list[dict] = [{"ticker": ticker, "twr": overall["twr"]}]
    else:
        windowTickers: list[Any] = (
            db.query(Transaction.ticker)
            .filter(
                Transaction.walletId == int(wallet.walletId),
                Transaction.date >= startDate,  # type: ignore[arg-type]
                Transaction.date <= endDate,  # type: ignore[arg-type]
            )
            .distinct()
            .all()
        )
        tickerRows = []
        for (rowTicker,) in windowTickers:
            tickerPerf = PerformanceManager.getPerformance(db, wallet, str(rowTicker), startDate, endDate)
            tickerRows.append({"ticker": str(rowTicker), "twr": tickerPerf["twr"]})
        tickerRows.sort(key=lambda row: row["twr"], reverse=True)

    worstTickers = sorted(tickerRows, key=lambda row: row["twr"])[:3]
    dividendLeg = overall["twr"] - overall["price_return"]
    gloss = (
        f"TWR {overall['twr']:.4f} from {startDate.isoformat()} to {endDate.isoformat()}; "
        f"price-only return {overall['price_return']:.4f}; dividend leg {dividendLeg:.4f} "
        f"(net dividends received {overall['dividends_received']:.2f})."
    )
    return {
        "from": startDate.isoformat(),
        "to": endDate.isoformat(),
        "ticker": ticker,
        "twr": overall["twr"],
        "twr_annualized": overall["twr_annualized"],
        "volatility": overall["volatility"],
        "dividends_received": overall["dividends_received"],
        "price_return": overall["price_return"],
        "dividend_leg": dividendLeg,
        "tickers": tickerRows,
        "worst_tickers": worstTickers,
        "gloss": gloss,
    }


@router.get("/progression-summary", operation_id="wallet_progression")
def wallet_progression_route(
    from_date: str | None = None,
    to_date: str | None = None,
    max_points: int = Query(default=120, ge=2, le=2000),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
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
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, from_date, to_date)
    series = AnalyticsManager.getProgression(db, wallet, startDate, endDate)
    points = series["points"]
    stride = max(1, ceil(len(points) / max_points))
    sampled = points[::stride]
    if points and sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return {
        "granularity": series["granularity"],
        "from": series["from"],
        "to": series["to"],
        "count": len(points),
        "returned": len(sampled),
        "stride": stride,
        "points": sampled,
    }


@router.get("/cashflows")
def get_cashflows_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getCashflows(db, wallet, startDate, endDate)


@router.get("/dividends/monthly")
def get_dividends_monthly_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(getWalletUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getDividendsMonthly(db, wallet, startDate, endDate)
