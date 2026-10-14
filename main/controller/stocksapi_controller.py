from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, Query, HTTPException, Response
from fastmcp import FastMCP

from main.app.stocks_api.query import queryCotations, queryFundamental, queryHistorical, queryLiveCotations
from main.app.stocks_api.key import verifyAPIKey
from main.app.stocks_api.util import categorizeColumns, generateAbbreviations
from main.app.stocks_api.compress import compressResponse, getNest
from main.app.stocks_api.cache import stocksCache
from main.utils.mcp_tools import mcpToolDecorator
from main.utils.sync_cache import sync_cache

logger = logging.getLogger(__name__)

STOCKS_TTL = "6h"
STOCKS_MAX_AGE = 6 * 3600
LIVE_TTL = "15s"
LIVE_MAX_AGE = 15

router = APIRouter(prefix="/stocks", tags=["Stocks API"])
mcp = FastMCP("Mansa Stocks MCP")

mcp_tool = mcpToolDecorator(mcp, router)


@router.get("/health")
def health():
    updatedAt = stocksCache.lastCacheUpdate
    ageHours = None
    if updatedAt is not None:
        ageHours = round((datetime.now(timezone.utc) - updatedAt).total_seconds() / 3600, 2)
    return {
        "status": "ok",
        "service": "stocksapi",
        "cacheReady": stocksCache.STOCKS_CACHE is not None,
        "cacheUpdatedAt": updatedAt.isoformat() if updatedAt is not None else None,
        "cacheAgeHours": ageHours,
    }


@mcp_tool
@router.get("/fields", operation_id="list_fields")
@sync_cache(ttl=STOCKS_TTL, key="stocks:fields")
def listFields(response: Response):
    """Discover available field names before querying get_historical or get_fundamental.

    IMPORTANT: Call this tool FIRST to get exact field names. Do NOT guess field names —
    they are dynamic and change when the database is updated.

    The response contains four categories:
    - "historical": object mapping field names to arrays of available years.
      Example: {"LUCRO LIQUIDO": [2020, 2021, 2022, 2023, 2024], "RECEITA LIQUIDA": [2020, ...]}
      Use these field names (without the year) in the get_historical tool's `fields` parameter.
    - "fundamental": array of available field names.
      Example: ["P/L", "P/VP", "ROE", "DY", "LIQUIDEZ CORRENTE"]
      Use these exact names in the get_fundamental tool's `fields` parameter.
    - "abbreviations": object mapping full names to short abbreviations.
      Example: {"LUCRO LIQUIDO": "LL", "P/L": "PL", "TICKER": "TK"}
      Use these abbreviations to decode compact responses (they appear when compact=true).
    - "nested": object describing JSON array fields and their subfield abbreviations.
      Example: {"NOTICIAS": {"subfields": {"TITULO": "T", "LINK": "L"}, "dropped_in_compact": ["LINK"]}}
      These subfields appear when compact=true.

    RESPONSE format:
    {
      "historical": {"FIELD_NAME": [year1, year2, ...], ...},
      "fundamental": ["FIELD1", "FIELD2", ...],
      "abbreviations": {"FULL_NAME": "ABBREV", ...},
      "nested": {"FIELD": {"subfields": {...}, "dropped_in_compact": [...], "max_items_compact": N}}
    }

    WORKFLOW:
    1. Call this FIRST to discover the available fields; never guess them
    2. Pick historical or fundamental names and pass them to the matching tool
    3. Use abbreviations from the response to decode compact responses
    4. Use nested docs to understand compressed subfields in NOTICIAS/DIVIDENDOS

    EXAMPLES:
    - "What fields are available?" → call list_fields with no arguments"""
    if stocksCache.STOCKS_CACHE is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")

    cols = stocksCache.STOCKS_CACHE.columns.tolist()
    historical, fundamental = categorizeColumns(cols)
    abbreviations = generateAbbreviations(historical, fundamental)
    nested = getNest(stocksCache.STOCKS_CACHE, stocksCache.nestedSample)

    response.headers["Cache-Control"] = f"public, max-age={STOCKS_MAX_AGE}"
    return {"historical": historical, "fundamental": fundamental, "abbreviations": abbreviations, "nested": nested}


@mcp_tool
@router.get("/historical", operation_id="get_historical")
@sync_cache(ttl=STOCKS_TTL, key="stocks:historical:{search}:{fields}:{dates}:{orderBy}:{limit}:{compact}")
def getHistorical(
    response: Response,
    search: str | None = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str | None = Query(None, max_length=500, pattern=r"^[A-Za-z0-9,\s/.-]+$"),
    dates: str | None = Query(None, max_length=21),
    orderBy: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    compact: bool = Query(False),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get year-based historical financial data for Brazilian B3 stocks.

    Returns financial metrics aggregated by year. Each data row contains
    TICKER, NOME, and selected metric columns named as "FIELD_NAME YEAR"
    (e.g. "LUCRO LIQUIDO 2023", "RECEITA LIQUIDA 2022").

    PARAMETERS:
    - `search` (optional): Comma-separated ticker symbols to filter.
      Examples: "PETR4", "PETR4,VALE3", "ITUB4,BBDC4". Case-insensitive.
      Supports prefix matching (e.g. "PET" matches PETR4, PETR3).
      If omitted, returns all stocks in the database. An empty request (no
      search/fields/dates) returns HTTP 400.

    - `fields` (optional): Comma-separated metric names (WITHOUT year suffix).
      Examples: "LUCRO LIQUIDO", "LUCRO LIQUIDO,RECEITA LIQUIDA,EBITDA".
      These must match the names returned by list_fields under "historical".
      If omitted, returns ALL available historical fields for the date range.

    - `dates` (optional): Year range in YYYY format, separated by comma.
      Single year: "2024" → returns only 2024 data.
      Year range: "2022,2024" → returns 2022, 2023, and 2024 data.
      If omitted, returns all available years in the database.
      NOTE: Full dates like "2024-01-01" are parsed but only the year component is used.

    - `orderBy` (optional): Sort results by a column name (descending).
    - `limit` (optional): Maximum number of stocks to return (1-1000).
    - `compact` (optional): Abbreviated keys and capped lists for chat.

    WORKFLOW:
    1. Call list_fields first to discover exact historical field names
    2. Pass those names plus a year range to this tool

    RESPONSE format:
    {
      "search": "PETR4",
      "fields": ["LUCRO LIQUIDO"],
      "dates": [2022, 2024],
      "type": "historical",
      "count": 1,
      "data": [{"TICKER": "PETR4", "NOME": "...", "LUCRO LIQUIDO 2024": 50000, ...}]
    }

    EXAMPLES:
    - Get PETR4 net income 2022-2024: search="PETR4", fields="LUCRO LIQUIDO", dates="2022,2024"
    - Get all revenue data for VALE3: search="VALE3", fields="RECEITA LIQUIDA"
    - Compare top 10 by EBITDA: fields="EBITDA", orderBy="EBITDA", limit=10"""
    response.headers["Cache-Control"] = f"public, max-age={STOCKS_MAX_AGE}"
    result = queryHistorical(search, fields, dates, orderBy, limit)
    if compact:
        result = compressResponse(
            result,
            "get_historical",
            {"search": search, "fields": fields, "dates": dates},
            stocksCache.STOCKS_CACHE,
            stocksCache.nestedSample,
        )
    return result


@mcp_tool
@router.get("/fundamental", operation_id="get_fundamental")
@sync_cache(ttl=STOCKS_TTL, key="stocks:fundamental:{search}:{fields}:{dates}:{orderBy}:{limit}:{compact}")
def getFundamental(
    response: Response,
    search: str | None = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str | None = Query(None, max_length=500, pattern=r"^[A-Za-z0-9,\s/.-]+$"),
    dates: str | None = Query(None, max_length=21),
    orderBy: str | None = Query(None),
    limit: int | None = Query(None, ge=1, le=1000),
    compact: bool = Query(False),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get point-in-time fundamental/valuation data for Brazilian B3 stocks.

    Returns valuation metrics and financial ratios at specific dates.
    Unlike get_historical (year-based), this tool works with exact dates
    and returns the most recent data available up to the requested date.

    PARAMETERS:
    - `search` (optional): Comma-separated ticker symbols to filter.
      Examples: "PETR4", "PETR4,VALE3", "ITUB4,BBDC4". Case-insensitive.
      Supports prefix matching (e.g. "PET" matches PETR4, PETR3).

    - `fields` (optional): Comma-separated metric names (point-in-time, no year suffix).
      Examples: "P/L", "P/L,ROE,DY", "P/VP,LIQUIDEZ CORRENTE".
      These must match the names returned by list_fields under "fundamental".
      If omitted, returns ALL available fundamental fields.

    - `dates` (optional): Date filter in one of these formats:
      * "YYYY" → returns data for the last available date in that year.
        Example: "2024" → most recent 2024 snapshot.
      * "YYYY-MM" → returns data for the last available date in that month.
        Example: "2024-06" → most recent June 2024 snapshot.
      * "YYYY-MM-DD" → returns data for that specific date or closest available.
        Example: "2024-01-15" → closest snapshot to Jan 15, 2024.
      * "START,END" → range: returns all snapshots between START and END dates.
        Example: "2024-01-01,2024-06-30" → all Q1-Q2 2024 snapshots.
      If omitted, returns the most recent snapshot for each stock. An empty
      request (no search/fields/dates) returns HTTP 400.

    - `orderBy` (optional): Sort results by a column name (descending).
    - `limit` (optional): Maximum number of stocks to return (1-1000).
    - `compact` (optional): Abbreviated keys and capped lists for chat.

    WORKFLOW:
    1. Call list_fields first to discover exact fundamental field names
    2. Pass those names plus an optional date to this tool

    RESPONSE format:
    {
      "search": "PETR4",
      "fields": ["P/L", "ROE"],
      "dates": "2024-01-15",
      "type": "fundamental",
      "count": 1,
      "data": [{"TICKER": "PETR4", "NOME": "...", "TIME": "2024-01-15", "P/L": 5.2, "ROE": 0.15}]
    }

    EXAMPLES:
    - Get PETR4 valuation: search="PETR4", fields="P/L,P/VP,ROE"
    - Get all stocks' dividend yield latest: fields="DY"
    - Compare P/L across tickers: search="PETR4,VALE3,ITUB4", fields="P/L", orderBy="P/L"
    - Q1 2024 fundamental snapshot: fields="P/L,ROE", dates="2024-01-01,2024-03-31" """
    response.headers["Cache-Control"] = f"public, max-age={STOCKS_MAX_AGE}"
    result = queryFundamental(search, fields, dates, orderBy, limit)
    if compact:
        result = compressResponse(
            result,
            "get_fundamental",
            {"search": search, "fields": fields, "dates": dates},
            stocksCache.STOCKS_CACHE,
            stocksCache.nestedSample,
        )
    return result


@mcp_tool
@router.get("/cotations", operation_id="get_cotations")
@sync_cache(ttl=STOCKS_TTL, key="stocks:cotations:{search}:{dates}:{adjusted}:{compact}:{max_points}")
def getCotations(
    response: Response,
    search: str = Query(..., min_length=1, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    dates: str | None = Query(None, max_length=21),
    adjusted: bool = Query(False),
    compact: bool = Query(False),
    max_points: int = Query(default=2000, ge=2, le=2000),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get 10-year daily price history (cotation) for Brazilian B3 stocks, downsampled to max_points.

    Returns a time series of daily closing prices for each requested ticker.
    Each ticker's data is a list of {DATA, PRECO} entries covering up to 10 years.

    PARAMETERS:
    - `search` (REQUIRED): Comma-separated ticker symbols.
      Examples: "PETR4", "PETR4,VALE3". Case-insensitive.

    - `dates` (optional): Date range to filter the price entries.
      Format: "YYYY-MM-DD,YYYY-MM-DD" (start,end).
      Example: "2020-01-01,2024-12-31" → only prices from 2020-2024.
      If omitted, returns the full 10-year price history.

    - `adjusted` (optional, default false):
      false → nominal prices (raw B3 data).
      true → inflation-adjusted prices (real returns).

    - `compact` (optional): Column-packed entries (h/d) for chat.
    - `max_points` (optional): Cap per-ticker daily entries, 2..2000, default 2000.

    RESPONSE format:
    {
      "search": "PETR4",
      "type": "cotations",
      "count": 1,
      "data": [{
        "TICKER": "PETR4",
        "NOME": "PETROBRAS PN",
        "TIME": "2024-01-15",
        "COTACAO 10Y PADRAO": [
          {"DATA": "15-01-2024", "PRECO": 28.50},
          {"DATA": "12-01-2024", "PRECO": 28.30},
          ...
        ]
      }]
    }

    WORKFLOW:
    1. Pass the tickers wanted; narrow with dates for a window
    2. stride>1: every nth day kept; first and last day always included
    3. Use compact for chat; use get_live_price for a single current price

    EXAMPLES:
    - Get PETR4 full price history: search="PETR4"
    - Get PETR4 + VALE3 2023 prices: search="PETR4,VALE3", dates="2023-01-01,2023-12-31"
    - Get inflation-adjusted prices: search="ITUB4", adjusted=true"""
    response.headers["Cache-Control"] = f"public, max-age={STOCKS_MAX_AGE}"
    result = queryCotations(search, dates, adjusted)
    rows = result.get("data")
    if isinstance(rows, list):
        for entry in rows:
            if not isinstance(entry, dict):
                continue
            cotationKey = next((key for key in entry if key.startswith("COTACAO")), None)
            if cotationKey is None or not isinstance(entry[cotationKey], list):
                continue
            entries = entry[cotationKey]
            if len(entries) > max_points:
                stride = (len(entries) + max_points - 1) // max_points
                sampled = entries[::stride]
                if sampled[-1] is not entries[-1]:
                    sampled.append(entries[-1])
                entry[cotationKey] = sampled
    if compact:
        result = compressResponse(
            result,
            "get_cotations",
            {"search": search, "dates": dates},
            stocksCache.STOCKS_CACHE,
            stocksCache.nestedSample,
        )
    return result


@mcp_tool
@router.get("/cotations/live", operation_id="get_live_price")
@sync_cache(ttl=LIVE_TTL, key="stocks:live:{search}:{compact}")
def getLiveCotation(
    response: Response,
    search: str = Query(..., min_length=1, max_length=7, pattern=r"^[A-Za-z0-9,\s]*$"),
    compact: bool = Query(False),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get real-time price quotation for a single Brazilian B3 stock.

    Returns the current (live) price directly from B3's trading system.
    Updates every 15 seconds during market hours. Only works for one ticker at a time.

    PARAMETERS:
    - `search` (REQUIRED): Single ticker symbol (4-5 characters).
      Examples: "PETR4", "VALE3", "ITUB4", "BBDC4".
      Must be an exact ticker — prefix matching is NOT supported for live quotes.

    - `compact` (optional): Abbreviated price keys (PA/PO/PMN/PMX/PMD) for chat.

    RESPONSE format:
    {
      "search": "PETR4",
      "type": "realtime-cotation",
      "timestamp": "2024-01-15T15:30:00",
      "count": 1,
      "data": [{
        "TICKER": "PETR4",
        "PRECO ATUAL": 28.50,
        "PRECO ORIGINAL": 28.30,
        "PRECO MINIMO": 28.00,
        "PRECO MAXIMO": 28.80,
        "PRECO MEDIO": 28.45
      }]
    }

    WORKFLOW:
    1. Pass one exact ticker; use get_cotations for history instead

    LIMITATIONS:
    - Only one ticker per request (max 7 chars for the search param).
    - Real-time data is only available during B3 market hours (10:00-17:30 BRT).
    - Outside market hours, returns the last available closing price.

    EXAMPLES:
    - Get live PETR4 price: search="PETR4"
    - Get live VALE3 price in compact form: search="VALE3", compact=true"""
    response.headers["Cache-Control"] = f"public, max-age={LIVE_MAX_AGE}"
    result = queryLiveCotations(search)
    if compact:
        result = compressResponse(
            result, "get_live_price", {"search": search}, stocksCache.STOCKS_CACHE, stocksCache.nestedSample
        )
    return result
