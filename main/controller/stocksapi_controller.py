from datetime import datetime, timezone
import logging

from cashews import cache
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import JSONResponse


from main.app.stocks_api.query import stocksQuery
from main.app.stocks_api.key import verifyAPIKey
from main.app.stocks_api.util import categorizeColumns, generateAbbreviations
from main.app.stocks_api.compress import compressResponse, getNest
from main.app.stocks_api.cache import stocksCache

logger = logging.getLogger(__name__)

cache.setup("mem://")

router = APIRouter(prefix="/stocks", tags=["Stocks API"])


def compressionState(request: Request) -> bool:
    return bool(getattr(request.state, "compressed", False))


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


@router.get("/fields", operation_id="list_fields")
def listFields():
    """Discover available field names before querying /historical or /fundamental.

    IMPORTANT: Call this tool FIRST to get exact field names. Do NOT guess field names —
    they are dynamic and change when the database is updated.

    The response contains four categories:
    - "historical": object mapping field names to arrays of available years.
      Example: {"LUCRO LIQUIDO": [2020, 2021, 2022, 2023, 2024], "RECEITA LIQUIDA": [2020, ...]}
      Use these field names (without the year) in the /historical endpoint's `fields` parameter.
    - "fundamental": array of available field names.
      Example: ["P/L", "P/VP", "ROE", "DY", "LIQUIDEZ CORRENTE"]
      Use these exact names in the /fundamental endpoint's `fields` parameter.
    - "abbreviations": object mapping full names to short abbreviations.
      Example: {"LUCRO LIQUIDO": "LL", "P/L": "PL", "TICKER": "TK"}
      Use these abbreviations in compact responses (they appear in compressed data).
    - "nested": object describing JSON array fields and their subfield abbreviations.
      Example: {"NOTICIAS": {"subfields": {"TITULO": "T", "LINK": "L"}, "dropped_in_compact": ["LINK"]}}
      These subfields appear when compact=true or X-MCP header is set.

    Response format:
    {
      "historical": {"FIELD_NAME": [year1, year2, ...], ...},
      "fundamental": ["FIELD1", "FIELD2", ...],
      "abbreviations": {"FULL_NAME": "ABBREV", ...},
      "nested": {"FIELD": {"subfields": {...}, "dropped_in_compact": [...], "max_items_compact": N}}
    }

    Typical workflow:
    1. Call this endpoint to get available fields
    2. Pick field names from the response
    3. Pass them to /historical or /fundamental via the `fields` parameter
    4. Use abbreviations from the response to decode compressed responses
    5. Use nested docs to understand compressed subfields in NOTICIAS/DIVIDENDOS"""
    if stocksCache.STOCKS_CACHE is None:
        raise HTTPException(status_code=503, detail="Cache not initialized")

    cols = stocksCache.STOCKS_CACHE.columns.tolist()
    historical, fundamental = categorizeColumns(cols)
    abbreviations = generateAbbreviations(historical, fundamental)
    nested = getNest()

    return {"historical": historical, "fundamental": fundamental, "abbreviations": abbreviations, "nested": nested}


@router.get("/historical", operation_id="get_historical")
@cache(ttl="1h", key="stocks:historical:{search}:{fields}:{dates}:{orderBy}:{limit}:{compact}:{compressed}")
async def getHistorical(
    request: Request,
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=500, pattern=r"^[A-Za-z0-9,\s/.-]+$"),
    dates: str = Query(None, max_length=21),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    compact: bool = Query(False),
    compressed: bool = Depends(compressionState),
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
      If omitted, returns all stocks in the database.

    - `fields` (optional): Comma-separated metric names (WITHOUT year suffix).
      Examples: "LUCRO LIQUIDO", "LUCRO LIQUIDO,RECEITA LIQUIDA,EBITDA".
      These must match the names returned by /stocks/fields under "historical".
      If omitted, returns ALL available historical fields for the date range.

    - `dates` (optional): Year range in YYYY format, separated by comma.
      Single year: "2024" → returns only 2024 data.
      Year range: "2022,2024" → returns 2022, 2023, and 2024 data.
      If omitted, returns all available years in the database.
      NOTE: Full dates like "2024-01-01" are parsed but only the year component is used.

    - `orderBy` (optional): Sort results by a column name (descending).
    - `limit` (optional): Maximum number of stocks to return (1-1000).

    WORKFLOW (recommended):
    1. Call /stocks/fields to discover available field names
    2. Pick the fields you need (historical section)
    3. Call this endpoint with those field names and a year range

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
    result = await stocksQuery.queryHistorical(search, fields, dates, orderBy, limit)
    if compact or compressed:
        result = compressResponse(result, "get_historical", {"search": search, "fields": fields, "dates": dates})
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/fundamental", operation_id="get_fundamental")
@cache(ttl="5m", key="stocks:fundamental:{search}:{fields}:{dates}:{orderBy}:{limit}:{compact}:{compressed}")
async def getFundamental(
    request: Request,
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=500, pattern=r"^[A-Za-z0-9,\s/.-]+$"),
    dates: str = Query(None, max_length=21),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    compact: bool = Query(False),
    compressed: bool = Depends(compressionState),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get point-in-time fundamental/valuation data for Brazilian B3 stocks.

    Returns valuation metrics and financial ratios at specific dates.
    Unlike /historical (year-based), this endpoint works with exact dates
    and returns the most recent data available up to the requested date.

    PARAMETERS:
    - `search` (optional): Comma-separated ticker symbols to filter.
      Examples: "PETR4", "PETR4,VALE3", "ITUB4,BBDC4". Case-insensitive.
      Supports prefix matching (e.g. "PET" matches PETR4, PETR3).

    - `fields` (optional): Comma-separated metric names (point-in-time, no year suffix).
      Examples: "P/L", "P/L,ROE,DY", "P/VP,LIQUIDEZ CORRENTE".
      These must match the names returned by /stocks/fields under "fundamental".
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
      If omitted, returns the most recent snapshot for each stock.

    - `orderBy` (optional): Sort results by a column name (descending).
    - `limit` (optional): Maximum number of stocks to return (1-1000).

    WORKFLOW (recommended):
    1. Call /stocks/fields to discover available field names
    2. Pick the fields you need (fundamental section)
    3. Call this endpoint with those field names and optional date

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
    result = await stocksQuery.queryFundamental(search, fields, dates, orderBy, limit)
    if compact or compressed:
        result = compressResponse(result, "get_fundamental", {"search": search, "fields": fields, "dates": dates})
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/cotations", operation_id="get_cotations")
@cache(ttl="5m", key="stocks:cotations:{search}:{dates}:{adjusted}:{compact}:{compressed}")
async def getCotations(
    request: Request,
    search: str = Query(..., min_length=1, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    dates: str = Query(None, max_length=21),
    adjusted: bool = Query(False),
    compact: bool = Query(False),
    compressed: bool = Depends(compressionState),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get 10-year daily price history (cotation) for Brazilian B3 stocks.

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

    EXAMPLES:
    - Get PETR4 full price history: search="PETR4"
    - Get PETR4 + VALE3 2023 prices: search="PETR4,VALE3", dates="2023-01-01,2023-12-31"
    - Get inflation-adjusted prices: search="ITUB4", adjusted=true"""
    result = await stocksQuery.queryCotations(search, dates, adjusted)
    if compact or compressed:
        result = compressResponse(result, "get_cotations", {"search": search, "dates": dates})
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/cotations/live", operation_id="get_live_price")
@cache(ttl="15s", key="stocks:live:{search}:{compact}:{compressed}")
async def getLiveCotation(
    request: Request,
    search: str = Query(..., min_length=1, max_length=7, pattern=r"^[A-Za-z0-9,\s]*$"),
    compact: bool = Query(False),
    compressed: bool = Depends(compressionState),
    apiKey: str = Depends(verifyAPIKey),
):
    """Get real-time price quotation for a single Brazilian B3 stock.

    Returns the current (live) price directly from B3's trading system.
    Updates every 15 seconds during market hours. Only works for one ticker at a time.

    PARAMETERS:
    - `search` (REQUIRED): Single ticker symbol (4-5 characters).
      Examples: "PETR4", "VALE3", "ITUB4", "BBDC4".
      Must be an exact ticker — prefix matching is NOT supported for live quotes.

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

    LIMITATIONS:
    - Only one ticker per request (max 7 chars for the search param).
    - Real-time data is only available during B3 market hours (10:00-17:30 BRT).
    - Outside market hours, returns the last available closing price."""
    result = await stocksQuery.queryLiveCotation(search)
    if compact or compressed:
        result = compressResponse(result, "get_live_price", {"search": search})
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=15"})
