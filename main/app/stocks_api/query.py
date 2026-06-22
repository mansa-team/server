import math
import re
from datetime import date, datetime
from fastapi import HTTPException
from typing import TYPE_CHECKING
import pandas as pd
import numpy as np
import json
import orjson

try:
    import yfinance as yf
except ImportError:
    yf = None  # type: ignore[assignment]

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import categorizeColumns, parseDateRange
import logging

logger = logging.getLogger(__name__)

B3_TICKER_PATTERN = re.compile(r"^[A-Z]{4}\d{1,2}$")


def sanitizeNanValues(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: sanitizeNanValues(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitizeNanValues(item) for item in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    if obj is pd.NA:
        return None
    return obj


if TYPE_CHECKING:
    from main.app.stocks_api.cache import StocksCacheManager


def _parseCotationDate(dataStr):
    """Parse DD-MM-YYYY from COTACAO 10Y JSON DATA field. ponytail: stdlib datetime only."""
    if not dataStr or not isinstance(dataStr, str):
        return None
    try:
        return datetime.strptime(dataStr, "%d-%m-%Y").date()
    except ValueError:
        return None


def _filterCotationByDate(entries, startDate, endDate):
    """Filter COTACAO 10Y JSON entries by their inner DATA field (DD-MM-YYYY)."""
    if not isinstance(entries, list) or not startDate or not endDate:
        return entries
    result = []
    for entry in entries:
        if isinstance(entry, dict):
            d = _parseCotationDate(entry.get("DATA"))
            if d and startDate <= d <= endDate:
                result.append(entry)
    return result


class StocksQueryManager:
    def __init__(self, cacheManager: "StocksCacheManager"):
        self.cacheManager = cacheManager

    SPECIAL_COLS = frozenset(["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"])

    def deserializeJsonColumns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()

        def cleanValue(val):
            if isinstance(val, float):
                try:
                    if math.isnan(val):
                        return None
                except (TypeError, ValueError):
                    pass
            elif pd.isna(val):
                return None
            return val

        def cleanJSON(obj):
            if isinstance(obj, dict):
                return {k: cleanJSON(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [cleanJSON(item) for item in obj]
            return cleanValue(obj)

        def parseJSON(x):
            try:
                return orjson.loads(x)
            except (ValueError, TypeError):
                return json.loads(x)

        for col in df.columns:
            if col in self.SPECIAL_COLS and (df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].apply(
                    lambda x: (
                        cleanJSON(parseJSON(x)) if isinstance(x, str) and x.startswith(("{", "[")) else cleanValue(x)
                    )
                )

        return df

    def filterBySearchTerms(self, df: pd.DataFrame, search: str) -> pd.DataFrame:
        if not search:
            return df

        searchTerms = [s.strip().upper() for s in search.split(",")]

        valid_indices = []
        for term in searchTerms:
            if term in self.cacheManager.tickerIndex:
                valid_indices.append(self.cacheManager.tickerIndex[term])

        if valid_indices:
            return df.iloc[valid_indices]

        mask = pd.Series([False] * len(df), index=df.index)
        for term in searchTerms:
            mask |= df["TICKER"].str.upper().str.startswith(term)
        return df[mask]

    def queryHistorical(
        self,
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
    ):
        if self.cacheManager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cacheManager.STOCKS_CACHE
            availableColumns = df.columns.tolist()
            availableColumnsSet = set(availableColumns)
            historicalFields, _ = categorizeColumns(availableColumns)

            if not historicalFields:
                raise HTTPException(status_code=400, detail="No historical data available in cache")

            fieldListAvailable = sorted(historicalFields.keys())
            fieldList = (
                fieldListAvailable
                if not fields
                else [f.strip() for f in fields.split(",") if f.strip() in fieldListAvailable]
            )

            availableYears = sorted(set(year for field in fieldList for year in historicalFields[field]))
            if dates:
                startDate, endDate = parseDateRange(dates)
                yearStart, yearEnd = startDate.year, endDate.year
            else:
                yearStart, yearEnd = availableYears[0], availableYears[-1]

            cols = ["TICKER", "NOME"] + [
                f"{field} {year}"
                for field in fieldList
                for year in range(yearEnd, yearStart - 1, -1)
                if f"{field} {year}" in availableColumnsSet
            ]

            if search:
                df = self.filterBySearchTerms(df, search)

            if "TIME" in df.columns:
                df = df.sort_values(by="TIME", ascending=False)

            if orderBy and orderBy in df.columns:
                df = df.sort_values(by=orderBy, ascending=False)

            if limit:
                df = df.head(limit)

            df = df[[c for c in cols if c in df.columns]]
            df = df.drop_duplicates(subset=["TICKER"], keep="first")

            df = self.deserializeJsonColumns(df)

            return {
                "search": search or "all",
                "fields": sorted(fieldList),
                "dates": [yearStart, yearEnd],
                "type": "historical",
                "count": len(df),
                "data": sanitizeNanValues(df.to_dict(orient="records")),
            }
        except Exception as e:
            logger.exception("Cached historical query failed")
            raise HTTPException(status_code=500, detail="Internal server error while processing historical data")

    def queryFundamental(
        self,
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
    ):
        if self.cacheManager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cacheManager.STOCKS_CACHE
            availableColumns = df.columns.tolist()
            availableColumnsSet = set(availableColumns)
            _, fundamentalCols = categorizeColumns(availableColumns)

            fieldList = (
                fundamentalCols
                if not fields
                else [f.strip() for f in fields.split(",") if f.strip() in fundamentalCols]
            )
            cols = ["TICKER", "NOME", "TIME"] + [field for field in fieldList if field in availableColumnsSet]

            if search:
                df = self.filterBySearchTerms(df, search)

            if "TIME" in df.columns:
                timeCol = pd.to_datetime(df["TIME"])

                if dates:
                    try:
                        startDate, endDate = parseDateRange(dates)
                        isRange = "," in dates
                        if isRange:
                            mask = (timeCol.dt.date >= startDate) & (timeCol.dt.date <= endDate)
                        else:
                            targetTs = pd.Timestamp(endDate)
                            diffs = (timeCol - targetTs).abs()
                            minDiff = diffs.min()
                            mask = diffs <= minDiff
                        df = df[mask]
                        timeCol = timeCol.loc[df.index]
                    except Exception as e:
                        logger.exception("Date parsing failed")
                        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

                sortIdx = timeCol.sort_values(ascending=False).index
                df = df.loc[sortIdx]
                df["TIME"] = timeCol.sort_values(ascending=False).dt.strftime("%Y-%m-%d")

            if not search or search.strip() == "":
                df = df.drop_duplicates(subset=["TICKER"], keep="first")

            if orderBy and orderBy in df.columns:
                df = df.sort_values(by=orderBy, ascending=False)

            if limit:
                df = df.head(limit)

            df = df[[c for c in cols if c in df.columns]]
            df = self.deserializeJsonColumns(df)

            return {
                "search": search or "all",
                "fields": fieldList,
                "dates": dates,
                "type": "fundamental",
                "count": len(df),
                "data": sanitizeNanValues(df.to_dict(orient="records")),
            }
        except Exception as e:
            logger.exception("Cached fundamental query failed")
            raise HTTPException(status_code=500, detail="Internal server error while processing fundamental data")

    def queryCotations(
        self,
        search: str | None = None,
        fields: str | None = None,  # ponytail: accepted for API consistency, unused (adjusted controls column)
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
        adjusted: bool = False,
    ):
        if self.cacheManager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cacheManager.STOCKS_CACHE
            targetCol = "COTACAO 10Y AJUSTADA" if adjusted else "COTACAO 10Y PADRAO"
            responseFields = [targetCol]

            if targetCol not in df.columns:
                return {
                    "search": search or "all",
                    "fields": responseFields,
                    "dates": dates,
                    "type": "cotations",
                    "count": 0,
                    "data": [],
                }

            if search:
                df = self.filterBySearchTerms(df, search)

            # Most recent row per TICKER (like /fundamental uses .iloc[0])
            if "TIME" in df.columns:
                df = df.sort_values(by="TIME", ascending=False)
            df = df.drop_duplicates(subset=["TICKER"], keep="first")

            cols = ["TICKER", "NOME", "TIME", targetCol]
            df = df[[c for c in cols if c in df.columns]]
            df = self.deserializeJsonColumns(df)

            # `dates` filters the INNER JSON DATA field, not the outer rows
            startDate, endDate = parseDateRange(dates)
            if startDate and endDate and targetCol in df.columns:
                df[targetCol] = df[targetCol].apply(
                    lambda entries: _filterCotationByDate(entries, startDate, endDate)
                )

            if orderBy and orderBy in df.columns:
                df = df.sort_values(by=orderBy, ascending=False)

            if limit:
                df = df.head(limit)

            return {
                "search": search or "all",
                "fields": responseFields,
                "dates": dates,
                "type": "cotations",
                "count": len(df),
                "data": sanitizeNanValues(df.to_dict(orient="records")),
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("Cached cotations query failed")
            raise HTTPException(status_code=500, detail="Internal server error while processing cotations data")

    def queryRealtimeCotation(self, search: str | None = None):
        """Fetch live prices for B3 tickers via yfinance.

        B3 tickers must match `^[A-Z]{4}\\d{1,2}$` (e.g., PETR4, VALE3).
        yfinance uses `.SA` suffix for Brazilian stocks (e.g., PETR4.SA).
        """
        if yf is None:
            raise HTTPException(status_code=503, detail="yfinance package not installed")

        if not search or not search.strip():
            raise HTTPException(status_code=400, detail="search parameter required (B3 tickers, e.g., PETR4)")

        tickers = [t.strip().upper() for t in search.split(",") if t.strip()]
        invalid = [t for t in tickers if not B3_TICKER_PATTERN.match(t)]
        if invalid:
            raise HTTPException(status_code=400, detail=f"Invalid B3 ticker(s): {', '.join(invalid)}")

        try:
            data = []
            for ticker in tickers:
                stock = yf.Ticker(f"{ticker}.SA").fast_info
                price = stock.get("last_price")
                prev = stock.get("previous_close")
                change_pct = ((price - prev) / prev) if (price is not None and prev not in (None, 0)) else None
                data.append(
                    {
                        "ticker": ticker,
                        "price": price,
                        "previous_close": prev,
                        "change_pct": change_pct,
                        "currency": stock.get("currency"),
                    }
                )
            return {
                "search": search,
                "type": "realtime-cotation",
                "count": len(data),
                "data": data,
            }
        except HTTPException:
            raise
        except Exception:
            logger.exception("Realtime cotation query failed")
            raise HTTPException(status_code=500, detail="Internal server error while fetching realtime data")


stocksQuery = StocksQueryManager(stocksCache)
