import logging
from functools import lru_cache

from sqlalchemy.orm import Session

from main.app.wallet.market_data import fetchCachedClose, fetchLivePrices
from main.app.wallet.wallets import getWallet
from main.models.wallet import Holding, Target

logger = logging.getLogger(__name__)

XANGO_WEIGHTS = {"underweight": 0.45, "rating": 0.25, "xango": 0.20, "momentum": 0.10}
BUY_THRESHOLD = 0.5


@lru_cache(maxsize=1024)
def fetchXangoScores(tickers: tuple[str, ...]) -> dict[str, float | None]:
    """XANGO quality score per ticker (0-100 scale).

    Stub: no HTTP score endpoint exists on STOCKS yet, so every ticker
    returns None and scoreBuyFlag redistributes the xango weight over the
    other inputs (flag degrades, never fails). When a real cached-score
    surface lands, only this body changes. Shared lru_cache is the
    freshness story; no staleness gate beyond it, YAGNI.
    """
    return {ticker: None for ticker in tickers}


def scoreBuyFlag(
    percentWallet: float,
    percentIdeal: float | None,
    holdingRating: int | None,
    xangoScore: float | None,
    appreciation: float | None,
) -> bool:
    """XANGO-informed buy flag (pure function, deterministic, no learned params).

    percentIdeal arrives on the 0-100 wire scale and is normalized to a
    fraction once at the comparison point. A None/NaN xangoScore is skipped
    and its weight redistributed proportionally over the other three inputs.
    XANGO informs the flag only — it never writes the manual rating.
    """
    if percentIdeal is None:
        return False
    percentIdealFrac = percentIdeal / 100
    underweight = max(0.0, (percentIdealFrac - percentWallet) / max(percentIdealFrac, 1e-9))
    underweight = min(1.0, underweight)
    if holdingRating is None:
        ratingInput = 0.5
    else:
        ratingInput = min(1.0, max(0.0, (holdingRating - 5) / 5))
    if xangoScore is None or xangoScore != xangoScore:  # None or NaN → skip input
        xangoInput: float | None = None
    else:
        xangoInput = min(1.0, max(0.0, xangoScore / 100))
    if appreciation is None:
        momentumInput = 0.5
    elif appreciation > 0:
        momentumInput = 1.0
    elif appreciation < 0:
        momentumInput = 0.0
    else:
        momentumInput = 0.5
    weights = XANGO_WEIGHTS
    if xangoInput is None:
        score = (
            weights["underweight"] * underweight + weights["rating"] * ratingInput + weights["momentum"] * momentumInput
        ) / (1.0 - weights["xango"])
    else:
        score = (
            weights["underweight"] * underweight
            + weights["rating"] * ratingInput
            + weights["xango"] * xangoInput
            + weights["momentum"] * momentumInput
        )
    return score >= BUY_THRESHOLD


def getPositions(db: Session, walletId: int, userId: int) -> dict:
    getWallet(db, walletId, userId)
    holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

    tickers = [str(holding.ticker) for holding in holdings]
    prices = fetchLivePrices(tickers)
    for ticker, price in list(prices.items()):
        if price is None:
            prices[ticker] = fetchCachedClose(ticker)

    equities: dict[str, float | None] = {}
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(str(holding.ticker))

        if price is None:
            equities[str(holding.ticker)] = None
        else:
            equities[str(holding.ticker)] = holdingQuantity * price

    equityTotal = sum(equity for equity in equities.values() if equity is not None)
    xangoScores = fetchXangoScores(tuple(tickers))

    items = []
    for holding in holdings:
        holdingQuantity = float(holding.quantity)
        holdingAvg = float(holding.avgPrice)
        price = prices.get(str(holding.ticker))
        equity = equities[str(holding.ticker)]

        if price is None or equity is None:
            currentPrice = None
            equityValue = None
            appreciation = None
        else:
            currentPrice = price
            equityValue = equity
            appreciation = equity - holdingQuantity * holdingAvg

        percentWallet = (equity / equityTotal) if equity is not None and equityTotal else 0
        target = (
            db.query(Target)
            .filter(Target.walletId == walletId, Target.keyKind == "ticker", Target.keyValue == holding.ticker)
            .first()
        )
        percentIdeal = float(target.percentIdeal) if target is not None else None
        holdingRating = holding.rating
        buyFlag = scoreBuyFlag(
            percentWallet,
            percentIdeal,
            holdingRating,  # type: ignore[arg-type]
            xangoScores.get(str(holding.ticker)),
            appreciation,
        )
        items.append(
            {
                "ticker": holding.ticker,
                "quantity": holdingQuantity,
                "avgPrice": holdingAvg,
                "current_price": currentPrice,
                "equity": equityValue,
                "appreciation": appreciation,
                "percent_wallet": percentWallet,
                "percent_ideal": percentIdeal,
                "buy_flag": buyFlag,
            }
        )
    return {"items": items, "equity_total": equityTotal}
