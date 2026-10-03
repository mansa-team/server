import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime

import requests
from cashews import cache as cashewsCache
from sqlalchemy.orm import Session

from config import Config
from main.app.stocks_api.sync_cache import cache as walletCache
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Holding, Target

logger = logging.getLogger(__name__)

cashewsCache.setup("mem://")

closesSemaphore = threading.BoundedSemaphore(8)


class PositionsManager:
    @classmethod
    @walletCache(ttl="6h", key="wallet:xango:{tickers}")
    def fetchXangoScores(cls, tickers: tuple[str, ...]) -> dict[str, float | None]:
        scores: dict[str, float | None] = {}
        for ticker in tickers:
            try:
                key = Config.STOCKS_API.KEY
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
    @walletCache(ttl="15s", key="wallet:live:{tickers}")
    def fetchLivePrices(cls, tickers: list[str]) -> dict[str, float | None]:
        if not tickers:
            return {}

        def one(ticker: str) -> tuple[str, float | None]:
            try:
                key = Config.STOCKS_API.KEY
                resp = requests.get(
                    f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/cotations/live",
                    params={"search": ticker, "compact": False},  # type: ignore[arg-type]
                    headers={"X-API-Key": key} if key else {},
                    timeout=3,
                )
                if resp.status_code == 429:
                    logger.warning("Live price quota exhausted for %s", ticker)
                    return ticker, None
                if resp.status_code != 200:
                    return ticker, None
                return ticker, float(resp.json()["data"][0]["PRECO ATUAL"])
            except Exception:
                return ticker, None

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
            return dict(pool.map(one, tickers))

    @classmethod
    def fillMissingCloses(cls, prices: dict[str, float | None]) -> dict[str, float | None]:
        missing = [ticker for ticker, price in prices.items() if price is None]
        if not missing:
            return prices

        def one(ticker: str) -> tuple[str, float | None]:
            with closesSemaphore:
                closes = cls.fetchPadraoCloses(ticker)
            return ticker, closes[-1][1] if closes else None

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(missing)))) as pool:
            for ticker, price in pool.map(one, missing):
                prices[ticker] = price
        return prices

    @classmethod
    def fetchMarketDividends(cls, ticker: str) -> list[dict]:
        try:
            key = os.getenv("STOCKS_API_KEY", "")
            resp = requests.get(
                f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/fundamental",
                params={"search": ticker, "fields": "HISTORICO DIVIDENDOS"},  # type: ignore[arg-type]
                headers={"X-API-Key": key} if key else {},
                timeout=3,
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()["data"]
            if payload and isinstance(payload[0], dict) and "HISTORICO DIVIDENDOS" in payload[0]:
                return payload[0]["HISTORICO DIVIDENDOS"]
            return payload
        except Exception:
            return []

    @classmethod
    @walletCache(ttl="6h", key="wallet:closes:{ticker}")
    def fetchPadraoCloses(cls, ticker: str) -> list[tuple[dateType, float]]:
        try:
            key = os.getenv("STOCKS_API_KEY", "")
            resp = requests.get(
                f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/cotations",
                params={"search": ticker},
                headers={"X-API-Key": key} if key else {},
                timeout=3,
            )
            if resp.status_code != 200:
                return []
            parsedCloses: list[tuple[dateType, float]] = []
            for closeRow in resp.json()["data"]:
                try:
                    parsedCloses.append(
                        (datetime.strptime(closeRow["DATA"], "%d-%m-%Y").date(), float(closeRow["PRECO"]))
                    )
                except Exception:
                    continue
            parsedCloses.sort(key=lambda closeItem: closeItem[0])
            return parsedCloses
        except Exception:
            return []

    @classmethod
    def pricePass(
        cls, db: Session, walletId: int, userId: int
    ) -> tuple[list[Holding], dict[str, float | None], dict[str, float | None], float]:
        WalletsManager.getWallet(db, walletId, userId)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

        tickers = sorted({str(holding.ticker) for holding in holdings})
        prices = cls.fetchLivePrices(tickers)
        cls.fillMissingCloses(prices)

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

        targetRows = db.query(Target).filter(Target.walletId == walletId, Target.keyKind == "ticker").all()
        targetByTicker = {str(target.keyValue): float(target.percentIdeal) for target in targetRows}

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
            percentIdeal = targetByTicker.get(str(holding.ticker))
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
            weight = cls.weightOf(holding)
            targetPct = (weight / weightTotal) if weightTotal else 0.0
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
