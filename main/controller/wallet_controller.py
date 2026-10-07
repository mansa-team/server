from fastapi import APIRouter, Depends, Query
from fastapi.responses import ORJSONResponse
from sqlalchemy.orm import Session

from config import getSession
from main.app.user.user import UserManager
from main.app.wallet import summary
from main.app.wallet.analytics import AnalyticsManager
from main.app.wallet.earnings import EarningsManager, serialize_earning
from main.app.wallet.entries import EntriesManager, EntryCreate, EntryUpdate, serialize_entry, serialize_holding
from main.app.wallet.performance import PerformanceManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.summary import RatingUpsert, SummaryManager
from main.app.wallet.wallets import Wallet, WalletCreate, WalletsManager

# Router-level gate: every wallet route requires an authenticated user.
# Per-route currentUser (in-process getCurrentUser, no HTTP introspect calls)
# supplies the userId; the wallet id always resolves server-side via getMyWallet.
router = APIRouter(prefix="/wallet", tags=["wallet"], dependencies=[Depends(UserManager.getCurrentUser)])


# Kept: FastAPI DI seam resolving the wallet for every wallet route — keep.
def getMyWallet(
    db: Session = Depends(getSession),
    currentUser: dict = Depends(UserManager.getCurrentUser),
) -> Wallet:
    return WalletsManager.getMyWallet(db, int(currentUser["userId"]))


@router.post("/wallets", response_class=ORJSONResponse, status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
):
    wallet = WalletsManager.createWallet(db, int(currentUser["userId"]), payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets", response_class=ORJSONResponse)
def list_wallets_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in WalletsManager.listWallets(db, int(currentUser["userId"]))
    ]


@router.post("/entries", response_class=ORJSONResponse, status_code=201)
def create_entry_route(
    payload: EntryCreate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.addEntry(db, wallet, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.get("/entries", response_class=ORJSONResponse)
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


@router.patch("/entries/{entryId}", response_class=ORJSONResponse)
def update_entry_route(
    entryId: int,
    payload: EntryUpdate,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    entry, holding = EntriesManager.updateEntry(db, wallet, entryId, payload)
    return {"entryId": entry.entryId, "holding": serialize_holding(holding)}


@router.delete("/entries/{entryId}", response_class=ORJSONResponse)
def delete_entry_route(
    entryId: int,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    deletedId, holding = EntriesManager.deleteEntry(db, wallet, entryId)
    return {"entryId": deletedId, "holding": serialize_holding(holding)}


@router.get("/positions", response_class=ORJSONResponse)
def list_positions_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return PositionsManager.getPositions(db, wallet)


@router.get("/rebalance", response_class=ORJSONResponse)
def get_rebalance_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return PositionsManager.getRebalance(db, wallet)


@router.get("/summary", response_class=ORJSONResponse)
def get_summary_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return SummaryManager.getSummary(db, wallet)


@router.get("/allocation", response_class=ORJSONResponse)
def get_allocation_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return SummaryManager.getAllocation(db, wallet)


@router.put("/ratings", response_class=ORJSONResponse)
def set_rating_route(
    payload: RatingUpsert,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    holding = summary.set_rating(db, wallet, payload)
    return {"ticker": holding.ticker, "rating": holding.rating}


@router.get("/earnings", response_class=ORJSONResponse)
def list_earnings_route(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    return {"items": [serialize_earning(item) for item in EarningsManager.listEarnings(db, wallet)]}


# Canonical raw: from/to + ticker only. Preset->date resolution and metric
# picking are client-side; TWR math + 6h cache stay server.
@router.get("/performance", response_class=ORJSONResponse)
def get_performance_route(
    ticker: str | None = None,
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return PerformanceManager.getPerformance(db, wallet, ticker, startDate, endDate)


# Canonical daily: bucketing + granularity selection are client-side.
@router.get("/progression", response_class=ORJSONResponse)
def get_progression_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getProgression(db, wallet, startDate, endDate)


@router.get("/cashflows", response_class=ORJSONResponse)
def get_cashflows_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getCashflows(db, wallet, startDate, endDate)


@router.get("/dividends/monthly", response_class=ORJSONResponse)
def get_dividends_monthly_route(
    fromIso: str | None = Query(default=None, alias="from"),
    toIso: str | None = Query(default=None, alias="to"),
    currentUser: dict = Depends(UserManager.getCurrentUser),
    wallet: Wallet = Depends(getMyWallet),
    db: Session = Depends(getSession),
):
    startDate, endDate = PerformanceManager.resolveWindowFromIso(db, wallet, fromIso, toIso)
    return AnalyticsManager.getDividendsMonthly(db, wallet, startDate, endDate)
