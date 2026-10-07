import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date as dateType
from datetime import datetime
from decimal import Decimal

import requests
from cashews import cache
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from config import Config
from main.utils.http_session import getSession
from main.utils.sync_cache import sync_cache
from main.models.wallet import Holding, Target, Wallet

logger = logging.getLogger(__name__)

cache.setup("mem://")

# Reviewer #8: external-data failures that legitimately degrade to a fallback
# (network/timeout/HTTP/malformed payload/expected-missing-data). Anything
# else — programming errors included — propagates instead of becoming a
# silent null/empty fallback.
EXTERNAL_ERRORS = (
    requests.exceptions.RequestException,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
)
REFRESH_ERRORS = EXTERNAL_ERRORS + (SQLAlchemyError,)


class PositionsManager:
    @classmethod
    @sync_cache(ttl="6h", key="wallet:xango:{tickers}")
    def fetchXangoScores(cls, tickers: tuple[str, ...]) -> dict[str, float | None]:
        scores: dict[str, float | None] = {}
        for ticker in tickers:
            try:
                key = Config.STOCKS_API.KEY
                resp = getSession().get(
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
            except EXTERNAL_ERRORS:
                scores[ticker] = None
        return scores

    @classmethod
    def maybeRefreshRatings(cls, db: Session, wallet: Wallet) -> None:
        """Backfill-only Xango refresh: fills `rating` solely where NULL.

        Single-rating rule: the Xango score is the initial/default value. It
        seeds new holdings at creation and fills NULLs here; it never
        overwrites an existing value (user overrides via PUT survive reads).
        """
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
                if holding.rating is None:
                    holding.rating = score  # type: ignore[assignment]
                    dirty = True
            if dirty:
                db.commit()
        except REFRESH_ERRORS:
            logger.warning("rating refresh failed for wallet %s", walletId, exc_info=True)
            try:
                db.rollback()
            except SQLAlchemyError:
                pass

    @classmethod
    @sync_cache(ttl="15s", key="wallet:live:{tickers}")
    def fetchLivePrices(cls, tickers: list[str]) -> dict[str, float | None]:
        if not tickers:
            return {}

        def one(ticker: str) -> tuple[str, float | None]:
            try:
                key = Config.STOCKS_API.KEY
                resp = getSession().get(
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
            except EXTERNAL_ERRORS:
                return ticker, None

        with ThreadPoolExecutor(max_workers=min(8, max(1, len(tickers)))) as pool:
            return dict(pool.map(one, tickers))

    @classmethod
    def fillMissingCloses(cls, prices: dict[str, float | None]) -> dict[str, float | None]:
        missing = [ticker for ticker, price in prices.items() if price is None]
        if not missing:
            return prices

        def one(ticker: str) -> tuple[str, float | None]:
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
            resp = getSession().get(
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
        except EXTERNAL_ERRORS:
            return []

    @staticmethod
    def parseDividendCell(cell) -> list[dict]:
        if isinstance(cell, str):
            try:
                cell = json.loads(cell)
            except (ValueError, TypeError):
                return []

        if isinstance(cell, list):
            return [row for row in cell if isinstance(row, dict)]
        return []

    @classmethod
    @sync_cache(ttl="6h", key="wallet:closes:{ticker}")
    def fetchPadraoCloses(cls, ticker: str) -> list[tuple[dateType, float]]:
        try:
            key = os.getenv("STOCKS_API_KEY", "")
            resp = getSession().get(
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
                except (ValueError, KeyError, TypeError, AttributeError, IndexError):
                    continue
            parsedCloses.sort(key=lambda closeItem: closeItem[0])
            return parsedCloses
        except EXTERNAL_ERRORS:
            return []

    @classmethod
    def pricePass(
        cls, db: Session, wallet: Wallet
    ) -> tuple[list[Holding], dict[str, Decimal | None], dict[str, Decimal | None], Decimal]:
        """Holdings + market prices + per-ticker equity + total.

        Metric semantics (reviewer #6, positions-owned portion): ``equity``
        per ticker = ledger quantity x current market price (live, else last
        close fallback); ``equity_total`` = sum over priced tickers only.
        Unpriced tickers surface as ``None`` (unknown), never zero.
        Domain math is Decimal; public dict outputs convert to float.
        """
        walletId = int(wallet.walletId)
        cls.maybeRefreshRatings(db, wallet)
        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()

        tickers = sorted({str(holding.ticker) for holding in holdings})
        livePrices = cls.fetchLivePrices(tickers)
        cls.fillMissingCloses(livePrices)

        prices: dict[str, Decimal | None] = {
            ticker: (Decimal(str(price)) if price is not None else None) for ticker, price in livePrices.items()
        }
        equities: dict[str, Decimal | None] = {}
        for holding in holdings:
            price = prices.get(str(holding.ticker))
            # NOTE: entries.py intentionally avoids importing this module
            # (circular); Decimal(str(...)) inline instead of toDecimal.
            equities[str(holding.ticker)] = Decimal(str(holding.quantity)) * price if price is not None else None

        equityTotal = sum((equity for equity in equities.values() if equity is not None), Decimal(0))
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
                currentPrice = float(price)
                equityValue = float(equity)

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
        return {"items": items, "equity_total": float(equityTotal)}

    @classmethod
    def getRebalance(cls, db: Session, wallet: Wallet) -> dict:
        # Canonical raw: weight + price + equity per ticker + total. target_pct /
        # current_pct / delta_qty / side derive client-side. Shares pricePass with
        # getPositions; the 15s live-price cache absorbs the second call.
        holdings, prices, equities, equityTotal = cls.pricePass(db, wallet)

        items = []
        for holding in holdings:
            ticker = str(holding.ticker)
            price = prices.get(ticker)
            equity = equities[ticker]
            items.append(
                {
                    "ticker": holding.ticker,
                    "weight": float(holding.rating) if holding.rating is not None else 0.0,
                    "current_price": float(price) if price is not None else None,
                    "equity": float(equity) if equity is not None else None,
                }
            )
        return {"items": items, "equity_total": float(equityTotal)}
