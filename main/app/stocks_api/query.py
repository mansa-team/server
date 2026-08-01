import math
import zstandard as zstd
from fastapi import HTTPException
import pandas as pd
import json
import orjson

from main.utils.http_session import getSession

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import categorizeColumns, parseDateRange

import logging

logger = logging.getLogger(__name__)


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


def filterCotationColumn(series: pd.Series, startDate, endDate) -> pd.Series:
    if not startDate or not endDate:
        return series

    startDateStr = startDate.strftime("%d-%m-%Y")
    endDateStr = endDate.strftime("%d-%m-%Y")

    exploded = series.explode()
    if exploded.empty or exploded.isna().all():
        return series

    dates = pd.to_datetime(exploded.str.get("DATA"), format="%d-%m-%Y", errors="coerce")
    mask = (dates >= pd.Timestamp(startDate)) & (dates <= pd.Timestamp(endDate))
    filtered = exploded[mask]

    result = [entries if not isinstance(entries, list) else [] for entries in series]
    for idx, group in filtered.groupby(level=0):
        result[series.index.get_loc(idx)] = group.tolist()

    return pd.Series(result, index=series.index)


class StocksQueryManager:
    filterCotationColumn = staticmethod(filterCotationColumn)

    def __init__(self, cacheManager):
        self.cacheManager = cacheManager

    SPECIAL_COLS = frozenset(["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"])

    def deserializeJsonColumns(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        df = df.copy()

        def cleanJSON(obj):
            if isinstance(obj, dict):
                return {k: cleanJSON(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [cleanJSON(item) for item in obj]
            return sanitizeNanValues(obj)

        def parseJSON(x):
            if isinstance(x, bytes):
                x = zstd.ZstdDecompressor().decompress(x).decode("utf-8")
            try:
                return orjson.loads(x)
            except (ValueError, TypeError):
                return json.loads(x)

        for col in df.columns:
            if col in self.SPECIAL_COLS and (df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col])):
                df[col] = df[col].apply(
                    lambda x: (
                        cleanJSON(parseJSON(x))
                        if (isinstance(x, str) and x.startswith(("{", "["))) or isinstance(x, bytes)
                        else sanitizeNanValues(x)
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

        mask = df["TICKER"].str.upper().apply(lambda t: any(t.startswith(term) for term in searchTerms))
        return df[mask]

    def queryHistorical(
        self,
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
    ):
        if not (search or fields or dates):
            raise HTTPException(status_code=400, detail="at least one of search/fields/dates required")
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
            if fields:
                requested = [f.strip() for f in fields.split(",") if f.strip()]
                invalid = [f for f in requested if f not in fieldListAvailable]
                if invalid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid fields: {invalid}. Use /stocks/fields to discover available names.",
                    )
                fieldList = requested
            else:
                fieldList = fieldListAvailable

            availableYears = sorted(set(year for field in fieldList for year in historicalFields[field]))
            if dates:
                startDate, endDate = parseDateRange(dates)
                if startDate is None or endDate is None:
                    raise ValueError(f"Invalid date range: {dates}")
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
        if not (search or fields or dates):
            raise HTTPException(status_code=400, detail="at least one of search/fields/dates required")
        if self.cacheManager.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")

        try:
            df = self.cacheManager.STOCKS_CACHE
            availableColumns = df.columns.tolist()
            availableColumnsSet = set(availableColumns)
            _, fundamentalCols = categorizeColumns(availableColumns)

            fundamentalColsFiltered = [
                c for c in fundamentalCols if c not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")
            ]
            if fields:
                requested = [f.strip() for f in fields.split(",") if f.strip()]
                invalid = [f for f in requested if f not in fundamentalCols]
                if invalid:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid fields: {invalid}. Use /stocks/fields to discover available names.",
                    )
                fieldList = [f for f in requested if f not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")]
            else:
                fieldList = fundamentalColsFiltered
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
                            df = df[mask]
                        else:
                            targetTs = pd.Timestamp(endDate)
                            diffs = (timeCol - targetTs).abs()
                            minDiffPerTicker = diffs.groupby(df["TICKER"]).transform("min")
                            mask = diffs == minDiffPerTicker
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
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("Cached fundamental query failed")
            raise HTTPException(status_code=500, detail="Internal server error while processing fundamental data")

    def queryCotations(
        self,
        search: str | None = None,
        dates: str | None = None,
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

            if "TIME" in df.columns:
                df = df.sort_values(by="TIME", ascending=False)
            df = df.drop_duplicates(subset=["TICKER"], keep="first")

            cols = ["TICKER", "NOME", "TIME", targetCol]
            df = df[[c for c in cols if c in df.columns]]
            df = self.deserializeJsonColumns(df)

            startDate, endDate = parseDateRange(dates)
            if startDate and endDate and targetCol in df.columns:
                df[targetCol] = filterCotationColumn(df[targetCol], startDate, endDate)

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

    def queryLiveCotation(self, search: str):
        try:
            resp = getSession().get(
                f"https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{search.upper()}",
                timeout=5,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            raise HTTPException(503, detail="B3 realtime unavailable")

        if payload.get("BizSts", {}).get("cd") != "OK" or not payload.get("Trad"):
            raise HTTPException(404, detail=f"Ticker {search.upper()} not found")

        dtTm = payload["Msg"]["dtTm"]
        raw = payload["Trad"][0]["scty"]["SctyQtn"]
        data = {
            "TICKER": payload["Trad"][0]["scty"]["symb"],
            "PRECO ATUAL": raw.get("curPrc"),
            "PRECO ORIGINAL": raw.get("opngPric"),
            "PRECO MINIMO": raw.get("minPric"),
            "PRECO MAXIMO": raw.get("maxPric"),
            "PRECO MEDIO": raw.get("avrgPric"),
        }

        return {
            "search": search.upper(),
            "type": "realtime-cotation",
            "timestamp": dtTm,
            "count": 1,
            "data": [data],
        }


stocksQuery = StocksQueryManager(stocksCache)
