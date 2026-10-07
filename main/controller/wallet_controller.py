from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.orm import Session

from config import getSession
from main.app.user.user import UserManager
from main.app.wallet.analytics import AnalyticsManager
from main.app.wallet.earnings import EarningsManager, serialize_earning
from main.app.wallet.entries import EntriesManager, EntryCreate, EntryUpdate, serialize_entry, serialize_holding
from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.summary import RatingUpsert, SummaryManager
from main.app.wallet.wallets import Wallet, WalletCreate, WalletsManager

# MCP auth: the `authorization` header param on MCP-exposed routes is not used
# by the handler itself — it puts the header in the OpenAPI schema so FastApiMCP
# pops args["authorization"] (injected by the agent dispatcher, never the LLM)
# into the replayed in-process request, where getCurrentUser verifies it.
router = APIRouter(prefix="/wallet", tags=["Wallet"], dependencies=[Depends(UserManager.getCurrentUser)])


def getMyWallet(
    db: Session = Depends(getSession),
    currentUser: dict = Depends(UserManager.getCurrentUser),
) -> Wallet:
    return WalletsManager.getMyWallet(db, int(currentUser["userId"]))


@router.post("/wallets", status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
):
    wallet = WalletsManager.createWallet(db, int(currentUser["userId"]), payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets")
def list_wallets_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in WalletsManager.listWallets(db, int(currentUser["userId"]))
    ]


@router.post("/entries", status_code=201)
def create_entry_route(
    payload: EntryCreate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
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
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    total, items = EntriesManager.listEntries(db, wallet, ticker, limit, offset)
    return {"total": total, "items": [serialize_entry(item) for item in items]}


@router.patch("/entries/{entryId}")
def update_entry_route(
    entryId: int,
    payload: EntryUpdate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.updateEntry(db, wallet, entryId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.delete("/entries/{entryId}")
def delete_entry_route(
    entryId: int,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    deletedId, holding = EntriesManager.deleteEntry(db, wallet, entryId)
    return {"entryId": deletedId, "holding": serialize_holding(holding)}


@router.get("/positions", operation_id="wallet_positions")
def list_positions_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return PositionsManager.getPositions(db, wallet)


@router.get("/rebalance", operation_id="wallet_rebalance")
def get_rebalance_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return PositionsManager.getRebalance(db, wallet)


@router.get("/summary", operation_id="wallet_summary")
def get_summary_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return SummaryManager.getSummary(db, wallet)


@router.get("/allocation", operation_id="wallet_allocation")
def get_allocation_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return SummaryManager.getAllocation(db, wallet)


@router.put("/ratings")
def set_rating_route(
    payload: RatingUpsert,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    """Single-rating override: PUT sets `Holding.rating` (Xango default, user-overwritable)."""
    holding = SummaryManager.set_rating(db, wallet, payload)
    return {"ticker": holding.ticker, "rating": holding.rating}


@router.get("/earnings", operation_id="wallet_earnings")
def list_earnings_route(
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return {"items": [serialize_earning(item) for item in EarningsManager.listEarnings(db, wallet)]}


@router.get("/performance", operation_id="wallet_performance")
def get_performance_route(
    ticker: str | None = None,
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return PerformanceManager.getPerformance(db, wallet, ticker, startDate, endDate)


@router.get("/progression", operation_id="wallet_progression_series")
def get_progression_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    authorization: str | None = Header(default=None),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getProgression(db, wallet, startDate, endDate)


@router.get("/cashflows")
def get_cashflows_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getCashflows(db, wallet, startDate, endDate)


@router.get("/dividends/monthly")
def get_dividends_monthly_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getDividendsMonthly(db, wallet, startDate, endDate)
