import math
import zstandard as zstd
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import HTTPException
import pandas as pd
import orjson
import requests
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from main.utils.http_session import getSession, isTransientError

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import JSON_COLUMNS, categorizeColumns, parseDateRange

import logging

logger = logging.getLogger(__name__)


def sanitizeNanValues(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {key: sanitizeNanValues(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [sanitizeNanValues(item) for item in obj]
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if obj is pd.NaT:
        return None
    if obj is pd.NA:
        return None
    return obj


def cotationDateKey(data) -> str | None:
    """Map a 'DD-MM-YYYY' DATA value to comparable 'YYYYMMDD', else None.

    String comparison on the key equals day-granularity date comparison and
    avoids pd.to_datetime on ~3k entries per request. Mirrors the old
    format='%d-%m-%Y'/errors='coerce' semantics: malformed values are
    excluded from the window rather than raising.
    """
    if not isinstance(data, str) or len(data) != 10 or data[2] != "-" or data[5] != "-":
        return None
    key = data[6:10] + data[3:5] + data[0:2]
    if not key.isdigit() or not ("01" <= key[4:6] <= "12" and "01" <= key[6:8] <= "31"):
        return None
    return key


def filterCotationColumn(series: pd.Series, startDate, endDate) -> pd.Series:
    if not startDate or not endDate:
        return series

    low = startDate.strftime("%Y%m%d")
    high = endDate.strftime("%Y%m%d")

    def inWindow(entries):
        if not isinstance(entries, list):
            return entries
        if not any(isinstance(entry, dict) for entry in entries):
            return entries
        return [
            entry
            for entry in entries
            if isinstance(entry, dict)
            and (key := cotationDateKey(entry.get("DATA"))) is not None
            and low <= key <= high
        ]

    return series.apply(inWindow)


def baseFrame(cacheManager=None):
    manager = cacheManager if cacheManager is not None else stocksCache
    snap = getattr(manager, "snapshot", None)
    pair = snap() if callable(snap) else None
    if isinstance(pair, tuple):
        df, tickerIndex = pair
    else:
        df, tickerIndex = manager.STOCKS_CACHE, manager.tickerIndex
    if df is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")
    return df, tickerIndex


def validateFields(requested: str | None, available: list, typeName: str) -> list:
    if not requested:
        return list(available)
    wanted = [field.strip() for field in requested.split(",") if field.strip()]
    invalid = [field for field in wanted if field not in available]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid fields: {invalid}. Use /stocks/fields to discover available names.",
        )
    return wanted


# Kept: public API response envelope shared by all query endpoints — keep.
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
        df = df[[column for column in cols if column in df.columns]]
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

    def parseJSON(cell, decompressor):
        if isinstance(cell, bytes):
            cell = decompressor.decompress(cell).decode("utf-8")
        try:
            return orjson.loads(cell)
        except (ValueError, TypeError):
            return cell

    decompressor = zstd.ZstdDecompressor()
    for col in df.columns:
        dtype = df[col].dtype
        if col in JSON_COLUMNS and (
            dtype == "object" or pd.api.types.is_string_dtype(dtype) or isinstance(dtype, pd.ArrowDtype)
        ):
            df[col] = df[col].apply(
                lambda cell: (
                    sanitizeNanValues(parseJSON(cell, decompressor))
                    if (isinstance(cell, str) and cell.startswith(("{", "["))) or isinstance(cell, bytes)
                    else sanitizeNanValues(cell)
                )
            )

    return df


def filterBySearchTerms(df: pd.DataFrame, search: str, index: dict | None = None) -> pd.DataFrame:
    if not search:
        return df

    searchTerms = [term.strip().upper() for term in search.split(",") if term.strip()]
    if not searchTerms:
        return df

    lookup = index if index is not None else stocksCache.tickerIndex
    upperTickers = df["TICKER"].str.upper()
    exactSet = {term for term in searchTerms if lookup and term in lookup}
    prefixTerms = tuple(term for term in searchTerms if term not in exactSet)
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
        historicalFields, ignored = categorizeColumns(availableColumns)

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
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
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
        ignored, fundamentalCols = categorizeColumns(availableColumns)

        fundamentalColsFiltered = [
            column for column in fundamentalCols if column not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")
        ]
        fieldList = (
            [
                field
                for field in validateFields(fields, fundamentalCols, "fundamental")
                if field not in ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA")
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
            except (ValueError, TypeError, KeyError, AttributeError):
                logger.exception("Date parsing failed")
                raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

        if not search or search.strip() == "":
            df = df.drop_duplicates(subset=["TICKER"], keep="first")

        return finalize(df, tickerIndex, search, orderBy, limit, cols, fieldList, dates, "fundamental")
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        logger.exception("Cached fundamental query failed")
        raise HTTPException(status_code=500, detail="Internal server error while processing fundamental data")


def queryCotations(
    search: str | None = None,
    dates: str | None = None,
    adjusted: bool = False,
    cacheManager=None,
):
    manager = cacheManager if cacheManager is not None else stocksCache
    df, tickerIndex = baseFrame(cacheManager)

    try:
        targetCol = "COTACAO 10Y AJUSTADA" if adjusted else "COTACAO 10Y PADRAO"
        responseFields = [targetCol]

        if targetCol not in df.columns:
            return envelope(search, responseFields, dates, "cotations", df.iloc[0:0])

        cols = ["TICKER", "NOME", "TIME", targetCol]
        # Fast path: exact tickers resolve to precomputed latest-snapshot rows,
        # skipping the full-frame boolean take (~300ms on 75k rows x 301 cols).
        # Sorted positions keep the stable-sort input order identical to the
        # filter path, so multi-ticker ordering is unchanged.
        side = getattr(manager, "cotationFrame", None)
        sideIndex = getattr(manager, "cotationIndex", None)
        terms = [term.strip().upper() for term in search.split(",") if term.strip()] if search else []
        if (
            isinstance(side, pd.DataFrame)
            and isinstance(sideIndex, dict)
            and targetCol in side.columns
            and all(term in sideIndex for term in terms)
        ):
            work = side.iloc[sorted(sideIndex[term] for term in dict.fromkeys(terms))] if terms else side
        else:
            # Fallback (prefix search or no side frame): project columns BEFORE
            # the boolean take so it copies 4 cols instead of 301 (~95ms).
            work = df[[column for column in cols if column in df.columns]]
            if search:
                work = filterBySearchTerms(work, search, tickerIndex)

        if "TIME" in work.columns:
            work = work.sort_values(by="TIME", ascending=False, kind="mergesort")
        work = work.drop_duplicates(subset=["TICKER"], keep="first")

        return finalize(
            work,
            tickerIndex,
            search,
            None,
            None,
            cols,
            responseFields,
            dates,
            "cotations",
            cotationCol=targetCol,
        )
    except HTTPException:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, IndexError):
        logger.exception("Cached cotations query failed")
        raise HTTPException(status_code=500, detail="Internal server error while processing cotations data")


def queryLiveCotations(search: str):
    """Single ticker or comma-separated tickers -> live B3 quotes, one code path.

    Input is normalized to a ticker list and every entry flows through the same
    concurrent fetch+parse loop. A one-ticker request returns the single-ticker
    realtime-cotation envelope (failures raise 404 unknown / 502 malformed /
    503 down); multi-ticker requests return the realtime-cotations envelope
    with per-ticker errors.
    """
    tickers = [term.strip().upper() for term in search.split(",") if term.strip()]
    if not tickers:
        raise HTTPException(status_code=400, detail="search required")

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(),
        retry=retry_if_exception(isTransientError),
        reraise=True,
    )
    def quote(symbol: str) -> tuple:
        """Single-ticker B3 GET (transient retry) + parse; 404 unknown, 502 malformed."""
        resp = getSession().get(
            f"https://cotacao.b3.com.br/mds/api/v1/instrumentQuotation/{symbol}",
            timeout=5,
        )
        resp.raise_for_status()
        payload = resp.json()
        try:
            trad = payload["Trad"]
        except (KeyError, TypeError):
            raise HTTPException(502, detail="B3 realtime malformed response")
        if payload.get("BizSts", {}).get("cd") != "OK" or not trad:
            raise HTTPException(404, detail=f"Ticker {symbol} not found")
        try:
            dtTm = payload["Msg"]["dtTm"]
        except (KeyError, TypeError):
            raise HTTPException(502, detail="B3 realtime malformed response")

        try:
            raw = trad[0]["scty"]["SctyQtn"]
            row = {
                "TICKER": trad[0]["scty"]["symb"],
                "PRECO ATUAL": raw.get("curPrc"),
                "PRECO ORIGINAL": raw.get("opngPric"),
                "PRECO MINIMO": raw.get("minPric"),
                "PRECO MAXIMO": raw.get("maxPric"),
                "PRECO MEDIO": raw.get("avrgPric"),
            }
        except (KeyError, TypeError, IndexError):
            raise HTTPException(502, detail="B3 realtime malformed response")
        return row, dtTm

    # B3 instrumentQuotation is a single-ticker URL with no batch param, so the
    # batch is one concurrent quote per deduped ticker; one ticker failing
    # never fails the batch.
    unique = list(dict.fromkeys(tickers))
    rows: dict = {}
    failures: dict = {}
    with ThreadPoolExecutor(max_workers=min(8, len(unique))) as pool:
        futures = {pool.submit(quote, ticker): ticker for ticker in unique}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                rows[ticker] = future.result()
            except requests.RequestException as exc:
                failures[ticker] = exc
            except HTTPException as exc:
                failures[ticker] = exc
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                failures[ticker] = exc

    if len(tickers) == 1:
        symbol = unique[0]
        if symbol in failures:
            failure = failures[symbol]
            if isinstance(failure, requests.RequestException):
                raise HTTPException(503, detail="B3 realtime unavailable")
            if isinstance(failure, HTTPException):
                raise failure
            raise HTTPException(502, detail="B3 realtime malformed response")
        row, dtTm = rows[symbol]
        return {
            "search": symbol,
            "type": "realtime-cotation",
            "timestamp": dtTm,
            "count": 1,
            "data": [row],
        }

    errors = {
        ticker: (
            "B3 realtime unavailable"
            if isinstance(failure, requests.RequestException)
            else failure.detail
            if isinstance(failure, HTTPException)
            else "B3 realtime malformed response"
        )
        for ticker, failure in failures.items()
    }
    data = [rows[ticker][0] for ticker in tickers if ticker not in errors]
    return {
        "search": ",".join(tickers),
        "type": "realtime-cotations",
        "count": len(data),
        "data": data,
        "errors": errors,
    }
