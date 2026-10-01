import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime

import requests

from config import Config

logger = logging.getLogger(__name__)


class MarketDataManager:
    @classmethod
    def fetchLivePrices(cls, tickers: list[str]) -> dict[str, float | None]:
        if not tickers:
            return {}

        def one(ticker: str) -> tuple[str, float | None]:
            try:
                key = os.getenv("STOCKS_API_KEY", "")
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
    def fetchCachedClose(cls, ticker: str) -> float | None:
        try:
            key = os.getenv("STOCKS_API_KEY", "")
            resp = requests.get(
                f"http://{Config.STOCKS_API.HOST}:{Config.STOCKS_API.PORT}/stocks/cotations",
                params={"search": ticker},
                headers={"X-API-Key": key} if key else {},
                timeout=3,
            )
            if resp.status_code == 429:
                logger.warning("Cached close quota exhausted for %s", ticker)
                return None
            if resp.status_code != 200:
                return None
            rows = resp.json()["data"]
            latest = max(rows, key=lambda row: datetime.strptime(row["DATA"], "%d-%m-%Y"))
            return float(latest["PRECO"])
        except Exception:
            return None

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
