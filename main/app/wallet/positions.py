import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime

import requests
from cashews import cache
from sqlalchemy.orm import Session

from config import Config
from main.utils.sync_cache import sync_cache
from main.models.wallet import Holding, Target, Wallet

logger = logging.getLogger(__name__)

cache.setup("mem://")

closesSemaphore = threading.BoundedSemaphore(8)


class PositionsManager:
    @classmethod
    @sync_cache(ttl="6h", key="wallet:xango:{tickers}")
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
                    scores[ticker] = min(max(float(row["XANGO INVESTING SCORE"]), 0.0), 100.0)
                else:
                    scores[ticker] = None
            except Exception:
                scores[ticker] = None
        return scores

    @classmethod
    def maybeRefreshRatings(cls, db: Session, wallet: Wallet) -> None:
        walletId = int(wallet.walletId)
        try:
            holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
            if not holdings:
                return
            tickers = tuple(sorted({str(holding.ticker) for holding in holdings}))
            scores = cls.fetchXangoScores(tickers)
            dirty = False
            for holding in holdings:
                score = scores.get(str(holding.ticker))
                if score is None:
                    continue
                if holding.rating is None or abs(float(holding.rating) - score) > 1e-9:
                    holding.rating = score  # type: ignore[assignment]
                    dirty = True
            if dirty:
                db.commit()
        except Exception:
            logger.warning("rating refresh failed for wallet %s", walletId, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass

    @classmethod
    @sync_cache(ttl="15s", key="wallet:live:{tickers}")
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
                timeout=10,
            )
            if resp.status_code != 200:
                return []
            payload = resp.json()["data"]
            if not isinstance(payload, list) or not payload:
                return []

            rows = [payload[0]] + [row for row in payload[1:] if isinstance(row, dict) and row is not payload[0]]
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if str(row.get("TICKER", ticker)).upper() != ticker.upper():
                    continue
                dividends = row.get("HISTORICO DIVIDENDOS")
                parsed = cls.parseDividendCell(dividends)
                if parsed:
                    return parsed
            # Fallback: first row with any parseable history (keeps prefix-match behavior).
            for row in rows:
                if not isinstance(row, dict):
                    continue
                parsed = cls.parseDividendCell(row.get("HISTORICO DIVIDENDOS"))
                if parsed:
                    return parsed
            return []
        except Exception:
            return []

    @staticmethod
    def parseDividendCell(cell) -> list[dict]:
        if isinstance(cell, str):
            try:
                cell = json.loads(cell)
            except ValueError:
                return []

        if isinstance(cell, list):
            return [row for row in cell if isinstance(row, dict)]
        return []

    @classmethod
    @sync_cache(ttl="6h", key="wallet:closes:{ticker}")
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
            payload = resp.json()["data"]
            if isinstance(payload, dict):
                payload = [payload]
            closeRows: list = []
            for item in payload if isinstance(payload, list) else []:
                if isinstance(item, dict):
                    nested = item.get("COTACAO 10Y PADRAO", item.get("COTACAO 10Y AJUSTADA"))
                    if isinstance(nested, list):
                        closeRows.extend(nested)
                        continue
                closeRows.append(item)
            parsedCloses: list[tuple[dateType, float]] = []
            for closeRow in closeRows:
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
        cls, db: Session, wallet: Wallet
    ) -> tuple[list[Holding], dict[str, float | None], dict[str, float | None], float]:
        walletId = int(wallet.walletId)
        cls.maybeRefreshRatings(db, wallet)
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
    def getPositions(cls, db: Session, wallet: Wallet) -> dict:
        # Canonical raw: holdings + live prices + per-ticker equity + total.
        # appreciation / percent_wallet / buy_flag derive client-side.
        holdings, prices, equities, equityTotal = cls.pricePass(db, wallet)
        walletId = int(wallet.walletId)

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
            else:
                currentPrice = price
                equityValue = equity

            items.append(
                {
                    "ticker": holding.ticker,
                    "quantity": holdingQuantity,
                    "avgPrice": holdingAvg,
                    "current_price": currentPrice,
                    "equity": equityValue,
                    "rating": float(holding.rating) if holding.rating is not None else 0.0,
                    "percent_ideal": targetByTicker.get(str(holding.ticker)),
                }
            )
        return {"items": items, "equity_total": equityTotal}

    @classmethod
    def getRebalance(cls, db: Session, wallet: Wallet) -> dict:
        # Canonical raw: weight + price + equity per ticker + total. target_pct /
        # current_pct / delta_qty / side derive client-side. Shares pricePass with
        # getPositions; the 15s live-price cache absorbs the second call.
        holdings, prices, equities, equityTotal = cls.pricePass(db, wallet)

        items = []
        for holding in holdings:
            ticker = str(holding.ticker)
            items.append(
                {
                    "ticker": holding.ticker,
                    "weight": float(holding.rating) if holding.rating is not None else 0.0,
                    "current_price": prices.get(ticker),
                    "equity": equities[ticker],
                }
            )
        return {"items": items, "equity_total": equityTotal}
