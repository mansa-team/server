import math
import zstandard as zstd
from fastapi import HTTPException
import pandas as pd
import orjson

from main.utils.http_session import getSession

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import JSON_COLUMNS, categorizeColumns, parseDateRange

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

    exploded = series.explode()
    if exploded.empty or exploded.isna().all():
        return series

    dates = pd.to_datetime(exploded.str.get("DATA"), format="%d-%m-%Y", errors="coerce")
    mask = (dates >= pd.Timestamp(startDate)) & (dates <= pd.Timestamp(endDate))

    grouped = exploded[mask].groupby(level=0).agg(list)
    base = pd.Series(
        [entries if not isinstance(entries, list) else [] for entries in series],
        index=series.index,
    )
    base.update(grouped)
    return base


def baseFrame(cacheManager=None):
    cm = cacheManager if cacheManager is not None else stocksCache
    snap = getattr(cm, "snapshot", None)
    pair = snap() if callable(snap) else None
    if isinstance(pair, tuple):
        df, tickerIndex = pair
    else:
        df, tickerIndex = cm.STOCKS_CACHE, cm.tickerIndex
    if df is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    return df, tickerIndex


def validateFields(requested: str | None, available: list, typeName: str) -> list:
    if not requested:
        return list(available)
    wanted = [f.strip() for f in requested.split(",") if f.strip()]
    invalid = [f for f in wanted if f not in available]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid fields: {invalid}. Use /stocks/fields to discover available names.",
        )
    return wanted


def envelope(search, fields, dates, typeName, df: pd.DataFrame):
    return {
        "search": search or "all",
        "fields": fields,
        "dates": dates,
        "type": typeName,
        "count": len(df),
        "data": sanitizeNanValues(df.to_dict(orient="records")),
    }


def finalize(
    df: pd.DataFrame,
    tickerIndex,
    search: str | None,
    orderBy: str | None,
    limit: int | None,
    cols: list[str] | None,
    fields,
    dates,
    typeName: str,
    dedupTickers: bool = False,
    cotationCol: str | None = None,
):
    if search:
        df = filterBySearchTerms(df, search, tickerIndex)
    if orderBy and orderBy in df.columns:
        df = df.sort_values(by=orderBy, ascending=False)
    if limit:
        df = df.head(limit)
    if cols is not None:
        df = df[[c for c in cols if c in df.columns]]
    if dedupTickers:
        df = df.drop_duplicates(subset=["TICKER"], keep="first")
    df = deserializeJsonColumns(df)
    if "TIME" in df.columns:
        df["TIME"] = pd.to_datetime(df["TIME"]).dt.strftime("%Y-%m-%d")
    if cotationCol and cotationCol in df.columns:
        startDate, endDate = parseDateRange(dates)
        if startDate and endDate:
            df[cotationCol] = filterCotationColumn(df[cotationCol], startDate, endDate)
    return envelope(search, fields, dates, typeName, df)


def deserializeJsonColumns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    df = df.copy()

    def parseJSON(x, decompressor):
        if isinstance(x, bytes):
            x = decompressor.decompress(x).decode("utf-8")
        try:
            return orjson.loads(x)
        except (ValueError, TypeError):
            return x

    decompressor = zstd.ZstdDecompressor()
    for col in df.columns:
        if col in JSON_COLUMNS and (df[col].dtype == "object" or pd.api.types.is_string_dtype(df[col])):
            df[col] = df[col].apply(
                lambda x: (
                    sanitizeNanValues(parseJSON(x, decompressor))
                    if (isinstance(x, str) and x.startswith(("{", "["))) or isinstance(x, bytes)
                    else sanitizeNanValues(x)
                )
            )

    return df


def filterBySearchTerms(df: pd.DataFrame, search: str, index: dict | None = None) -> pd.DataFrame:
    if not search:
        return df

    searchTerms = [s.strip().upper() for s in search.split(",") if s.strip()]
    if not searchTerms:
        return df

    lookup = index if index is not None else stocksCache.tickerIndex
    upperTickers = df["TICKER"].str.upper()
    exactSet = {t for t in searchTerms if lookup and t in lookup}
    prefixTerms = tuple(t for t in searchTerms if t not in exactSet)
    exactMask = upperTickers.isin(exactSet)
    if prefixTerms:
        return df[exactMask | upperTickers.str.startswith(prefixTerms)]
    return df[exactMask]


def queryHistorical(
    search: str | None = None,
    fields: str | None = None,
    dates: str | None = None,
    orderBy: str | None = None,
    limit: int | None = None,
    cacheManager=None,
):
    if not (search or fields or dates):
        raise HTTPException(status_code=400, detail="at least one of search/fields/dates required")
    df, tickerIndex = baseFrame(cacheManager)

    try:
        availableColumns = df.columns.tolist()
        availableColumnsSet = set(availableColumns)
        historicalFields, _ = categorizeColumns(availableColumns)

        if not historicalFields:
            raise HTTPException(status_code=400, detail="No historical data available in cache")

        fieldList = validateFields(fields, sorted(historicalFields.keys()), "historical")

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

        return finalize(
            df,
            tickerIndex,
            search,
            orderBy,
            limit,
            cols,
            sorted(fieldList),
            [yearStart, yearEnd],
            "historical",
            dedupTickers=True,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cached historical query failed")
        raise HTTPException(status_code=500, detail="Internal server error while processing historical data")


def queryFundamental(
    search: str | None = None,
    fields: str | None = None,
    dates: str | None = None,
    orderBy: str | None = None,
    limit: int | None = None,
    cacheManager=None,
):
    if not (search or fields or dates):
        raise HTTPException(status_code=400, detail="at least one of search/fields/dates required")
    df, tickerIndex = baseFrame(cacheManager)

    try:
        availableColumns = df.columns.tolist()
        availableColumnsSet = set(availableColumns)
        _, fundamentalCols = categorizeColumns(availableColumns)

        fundamentalColsFiltered = [
            c for c in fundamentalCols if c not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")
        ]
        fieldList = (
            [
                f
                for f in validateFields(fields, fundamentalCols, "fundamental")
                if f not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")
            ]
            if fields
            else fundamentalColsFiltered
        )
        cols = ["TICKER", "NOME", "TIME"] + [field for field in fieldList if field in availableColumnsSet]

        if search:
            df = filterBySearchTerms(df, search, tickerIndex)

        if "TIME" in df.columns and dates:
            timeCol = pd.to_datetime(df["TIME"])
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
            except Exception:
                logger.exception("Date parsing failed")
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        if not search or search.strip() == "":
            df = df.drop_duplicates(subset=["TICKER"], keep="first")

        return finalize(df, tickerIndex, search, orderBy, limit, cols, fieldList, dates, "fundamental")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cached fundamental query failed")
        raise HTTPException(status_code=500, detail="Internal server error while processing fundamental data")


def queryCotations(
    search: str | None = None,
    dates: str | None = None,
    adjusted: bool = False,
    cacheManager=None,
):
    df, tickerIndex = baseFrame(cacheManager)

    try:
        targetCol = "COTACAO 10Y AJUSTADA" if adjusted else "COTACAO 10Y PADRAO"
        responseFields = [targetCol]

        if targetCol not in df.columns:
            return envelope(search, responseFields, dates, "cotations", df.iloc[0:0])

        if search:
            df = filterBySearchTerms(df, search, tickerIndex)

        if "TIME" in df.columns:
            df = df.sort_values(by="TIME", ascending=False, kind="mergesort")
        df = df.drop_duplicates(subset=["TICKER"], keep="first")

        return finalize(
            df,
            tickerIndex,
            search,
            None,
            None,
            ["TICKER", "NOME", "TIME", targetCol],
            responseFields,
            dates,
            "cotations",
            cotationCol=targetCol,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Cached cotations query failed")
        raise HTTPException(status_code=500, detail="Internal server error while processing cotations data")


def queryLiveCotation(search: str):
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
