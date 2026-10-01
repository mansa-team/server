import logging
import os

import requests
from cashews import cache as cashewsCache
from sqlalchemy.orm import Session

from config import Config
from main.app.stocks_api.sync_cache import cache as walletCache
from main.app.wallet.market_data import MarketDataManager
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Holding, Target

logger = logging.getLogger(__name__)

cashewsCache.setup("mem://")


class PositionsManager:
    @classmethod
    @walletCache(ttl="6h", key="wallet:xango:{tickers}")
    def fetchXangoScores(cls, tickers: tuple[str, ...]) -> dict[str, float | None]:
        """XANGO quality score per ticker (0-100 scale).

        One fundamental read per ticker; any per-ticker failure degrades to
        None and scoreBuyFlag redistributes the xango weight over the other
        inputs (flag degrades, never fails). Shared cashews entry is the
        freshness story; no staleness gate beyond it, YAGNI.
        """
        scores: dict[str, float | None] = {}
        for ticker in tickers:
            try:
                key = os.getenv("STOCKS_API_KEY", "")
                resp = requests.get(
                    f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/fundamental",
                    params={"search": ticker, "fields": "XANGO INVESTING SCORE", "compact": False},  # type: ignore[arg-type]
                    headers={"X-API-Key": key} if key else {},
                    timeout=3,
                )
                if resp.status_code != 200:
                    scores[ticker] = None
                    continue
                payload = resp.json()["data"]
                row = payload[0] if payload else None
                if isinstance(row, dict) and "XANGO INVESTING SCORE" in row:
                    scores[ticker] = float(row["XANGO INVESTING SCORE"])
                else:
                    scores[ticker] = None
            except Exception:
                scores[ticker] = None
        return scores

    @classmethod
    def weightOf(cls, holding: Holding) -> float:
        return float(holding.rating) if holding.rating is not None else 0.0

    @classmethod
    def pricePass(
        cls, db: Session, walletId: int, userId: int
    ) -> tuple[list[Holding], dict[str, float | None], dict[str, float | None], float]:
        WalletsManager.getWallet(db, walletId, userId)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

        tickers = [str(holding.ticker) for holding in holdings]
        prices = MarketDataManager.fetchLivePrices(tickers)
        for ticker, price in list(prices.items()):
            if price is None:
                closes = MarketDataManager.fetchPadraoCloses(ticker)
                prices[ticker] = closes[-1][1] if closes else None

        equities: dict[str, float | None] = {}
        for holding in holdings:
            price = prices.get(str(holding.ticker))
            equities[str(holding.ticker)] = float(holding.quantity) * price if price is not None else None

        equityTotal = sum(equity for equity in equities.values() if equity is not None)
        return holdings, prices, equities, equityTotal

    @classmethod
    def rebalanceDeltas(
        cls, holdings: list[Holding], equities: dict[str, float | None], equityTotal: float
    ) -> dict[str, float | None]:
        """Weight-share deltas on backend floats: target_i = w_i/Σw, targetEquity = target_i × equityTotal, delta = targetEquity − equity. Σw=0 → all deltas null."""
        weightTotal = sum(cls.weightOf(holding) for holding in holdings)
        deltas: dict[str, float | None] = {}
        for holding in holdings:
            ticker = str(holding.ticker)
            equity = equities.get(ticker)
            if not weightTotal or equity is None:
                deltas[ticker] = None
            else:
                deltas[ticker] = cls.weightOf(holding) / weightTotal * equityTotal - equity
        return deltas

    @classmethod
    def getPositions(cls, db: Session, walletId: int, userId: int) -> dict:
        holdings, prices, equities, equityTotal = cls.pricePass(db, walletId, userId)
        deltas = cls.rebalanceDeltas(holdings, equities, equityTotal)

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
            delta = deltas[str(holding.ticker)]
            buyFlag = delta is not None and delta > 0
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

    @classmethod
    def getRebalance(cls, db: Session, walletId: int, userId: int) -> dict:
        holdings, prices, equities, equityTotal = cls.pricePass(db, walletId, userId)
        deltas = cls.rebalanceDeltas(holdings, equities, equityTotal)
        weightTotal = sum(cls.weightOf(holding) for holding in holdings)

        items = []
        for holding in holdings:
            ticker = str(holding.ticker)
            weightFloat = cls.weightOf(holding)
            # Display rounds to int; all math above stays on backend floats.
            weight = int(round(weightFloat))
            targetPct = (weightFloat / weightTotal) if weightTotal else 0.0
            equity = equities[ticker]
            currentPct = (equity / equityTotal) if equity is not None and equityTotal else 0.0
            delta = deltas[ticker]
            price = prices.get(ticker)
            if delta is None or price is None:
                deltaEquity = None
                deltaQty = None
                side = "hold"
            else:
                deltaEquity = delta
                deltaQty = delta / price
                side = "buy" if delta > 0 else "sell" if delta < 0 else "hold"
            items.append(
                {
                    "ticker": holding.ticker,
                    "weight": weight,
                    "target_pct": targetPct,
                    "current_pct": currentPct,
                    "delta_equity": deltaEquity,
                    "delta_qty": deltaQty,
                    "side": side,
                }
            )
        return {"items": items, "equity_total": equityTotal}
