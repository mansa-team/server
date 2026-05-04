import math
from fastapi import HTTPException
from typing import TYPE_CHECKING
import pandas as pd
import numpy as np
import json

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import categorizeColumns, parseYearInput

if TYPE_CHECKING:
    from main.app.stocks_api.cache import StocksCacheManager


class StocksQueryManager:
    def __init__(self, cache_manager: "StocksCacheManager"):
        self.cache_manager = cache_manager

    SPECIAL_COLS = frozenset([
        "COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA",
        "HISTORICO DIVIDENDOS", "NOTICIAS"
    ])

    def deserializeJsonColumns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()

        def replaceNan(obj):
            if isinstance(obj, dict):
                return {k: replaceNan(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [replaceNan(item) for item in obj]
            elif isinstance(obj, float):
                try:
                    if math.isnan(obj):
                        return None
                except (TypeError, ValueError):
                    pass
            elif pd.isna(obj):
                return None
            return obj

        for col in df.columns:
            if col in self.SPECIAL_COLS and df[col].dtype == "object":
                df[col] = df[col].apply(
                    lambda x: replaceNan(json.loads(x)) if isinstance(x, str) and x.startswith(("{", "[")) else x
                )

        return df

    def filterBySearchTerms(self, df: pd.DataFrame, search: str) -> pd.DataFrame:
        if not search:
            return df
        searchTerms = [s.strip().upper() for s in search.split(",")]
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
        if self.cache_manager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cache_manager.STOCKS_CACHE.copy()
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
            yearStart, yearEnd = parseYearInput(dates) if dates else (availableYears[0], availableYears[-1])

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
                "data": df.to_dict(orient="records"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cached historical error: {str(e)}")

    def queryFundamental(
        self,
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
    ):
        if self.cache_manager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cache_manager.STOCKS_CACHE.copy()
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
                time_col = pd.to_datetime(df["TIME"])

                if dates:
                    try:
                        dateRange = [d.strip() for d in dates.split(",")]
                        if len(dateRange) == 2:
                            startDate = pd.to_datetime(dateRange[0]).date()
                            endDate = pd.to_datetime(dateRange[1]).date()
                            mask = (time_col.dt.date >= startDate) & (time_col.dt.date <= endDate)
                            df = df[mask]
                        elif len(dateRange) == 1:
                            targetDate = pd.to_datetime(dateRange[0]).date()
                            df = df[time_col.dt.date == targetDate]
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Data format error (YYYY-MM-DD): {str(e)}")

                df["TIME"] = time_col.dt.strftime("%Y-%m-%d")
                df = df.sort_values(by="TIME", ascending=False)

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
                "data": df.to_dict(orient="records"),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Cached fundamental error: {str(e)}")

stocksQuery = StocksQueryManager(stocksCache)