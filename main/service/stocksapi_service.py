import logging
from typing import Annotated

from fastapi import HTTPException
from fastmcp import FastMCP
from pydantic import Field

from main.utils.service_manager import getApp
from main.controller.stocksapi_controller import router as stocksRouter

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.compress import compressResponse, getNest
from main.app.stocks_api.query import queryCotations, queryFundamental, queryHistorical, queryLiveCotations
from main.app.stocks_api.util import categorizeColumns, generateAbbreviations

logger = logging.getLogger(__name__)


class StocksAPIService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(stocksRouter)

        stocksMcp = buildStocksMCP()
        mcpApp = stocksMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        service.mount("/stocks/mcp", mcpApp)

        stocksCache.cacheScheduler()


def buildStocksMCP() -> FastMCP:
    """Hand-written stocks MCP server: 5 thin public tools delegating to query fns."""
    mcp = FastMCP("Mansa Stocks MCP")

    @mcp.tool
    def list_fields() -> dict:
        """Discover available field names before querying get_historical or get_fundamental.

        PARAMETERS:
        - None: returns the full historical/fundamental field catalog with abbreviations.

        RESPONSE format:
        {"historical": {"FIELD_NAME": [year1, year2, ...]}, "fundamental": ["FIELD1", ...], "abbreviations": {"FULL_NAME": "ABBREV"}, "nested": {...}}

        WORKFLOW:
        1. Call this FIRST to get exact field names; never guess them
        2. Pick historical or fundamental names and pass them to the matching tool
        3. Use abbreviations to decode compact responses

        EXAMPLES:
        - "What fields are available?" → call list_fields with no arguments
        """
        if stocksCache.STOCKS_CACHE is None:
            raise HTTPException(status_code=503, detail="Cache not initialized")
        cols = stocksCache.STOCKS_CACHE.columns.tolist()
        historical, fundamental = categorizeColumns(cols)
        abbreviations = generateAbbreviations(historical, fundamental)
        nested = getNest(stocksCache.STOCKS_CACHE, stocksCache.nestedSample)
        return {"historical": historical, "fundamental": fundamental, "abbreviations": abbreviations, "nested": nested}

    @mcp.tool
    def get_historical(
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
        compact: bool = False,
    ) -> dict:
        """Get year-based historical financial data for Brazilian B3 stocks.

        PARAMETERS:
        - `search` (optional): Comma-separated tickers, e.g. "PETR4,VALE3".
        - `fields` (optional): Comma-separated metric names WITHOUT year suffix.
        - `dates` (optional): Year range "YYYY" or "YYYY,YYYY".
        - `orderBy` (optional): Sort results by a column name (descending).
        - `limit` (optional): Maximum stocks to return (1-1000).
        - `compact` (optional): Abbreviated keys and capped lists for chat.

        RESPONSE format:
        {"search": "PETR4", "fields": ["LUCRO LIQUIDO"], "dates": [2022, 2024], "type": "historical", "count": 1, "data": [...]}

        WORKFLOW:
        1. Call list_fields first to discover exact historical field names
        2. Pass those names plus a year range to this tool

        EXAMPLES:
        - Get PETR4 net income 2022-2024: search="PETR4", fields="LUCRO LIQUIDO", dates="2022,2024"
        - Compare top 10 by EBITDA: fields="EBITDA", orderBy="EBITDA", limit=10
        """
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

    @mcp.tool
    def get_fundamental(
        search: str | None = None,
        fields: str | None = None,
        dates: str | None = None,
        orderBy: str | None = None,
        limit: int | None = None,
        compact: bool = False,
    ) -> dict:
        """Get point-in-time fundamental/valuation data for Brazilian B3 stocks.

        PARAMETERS:
        - `search` (optional): Comma-separated tickers, e.g. "PETR4,VALE3".
        - `fields` (optional): Comma-separated metric names, e.g. "P/L,ROE,DY".
        - `dates` (optional): "YYYY", "YYYY-MM", "YYYY-MM-DD" or "START,END" range.
        - `orderBy` (optional): Sort results by a column name (descending).
        - `limit` (optional): Maximum stocks to return (1-1000).
        - `compact` (optional): Abbreviated keys and capped lists for chat.

        RESPONSE format:
        {"search": "PETR4", "fields": ["P/L", "ROE"], "type": "fundamental", "count": 1, "data": [...]}

        WORKFLOW:
        1. Call list_fields first to discover exact fundamental field names
        2. Pass those names plus an optional date to this tool

        EXAMPLES:
        - Get PETR4 valuation: search="PETR4", fields="P/L,P/VP,ROE"
        - Compare P/L across tickers: search="PETR4,VALE3,ITUB4", fields="P/L", orderBy="P/L"
        """
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

    @mcp.tool
    def get_cotations(
        search: str,
        dates: str | None = None,
        adjusted: bool = False,
        compact: bool = False,
        max_points: Annotated[int, Field(ge=2, le=2000)] = 2000,
    ) -> dict:
        """Get 10-year daily price history for Brazilian B3 stocks (downsampled to max_points).

        PARAMETERS:
        - `search` (required): Comma-separated tickers, e.g. "PETR4,VALE3".
        - `dates` (optional): Date range "YYYY-MM-DD,YYYY-MM-DD".
        - `adjusted` (optional): True for inflation-adjusted prices, default false.
        - `compact` (optional): Column-packed entries (h/d) for chat.
        - `max_points` (optional): Cap per-ticker daily entries, 2..2000, default 2000.

        RESPONSE format:
        {"search": "PETR4", "type": "cotations", "count": 1, "data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": [{"DATA": "15-01-2024", "PRECO": 28.5}]}]}

        WORKFLOW:
        1. Pass the tickers wanted; narrow with dates for a window
        2. stride>1: every nth day kept; first and last day always included

        EXAMPLES:
        - Get PETR4 full price history: search="PETR4"
        - Get PETR4 + VALE3 2023 prices: search="PETR4,VALE3", dates="2023-01-01,2023-12-31"
        - Get inflation-adjusted prices: search="ITUB4", adjusted=true
        """
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

    @mcp.tool
    def get_live_price(search: str, compact: bool = False) -> dict:
        """Get real-time price quotation for Brazilian B3 stocks.

        PARAMETERS:
        - `search` (required): Single ticker symbol, e.g. "PETR4".
        - `compact` (optional): Abbreviated price keys (PA/PO/PMN/PMX/PMD) for chat.

        RESPONSE format:
        {"search": "PETR4", "type": "realtime-cotation", "count": 1, "data": [{"TICKER": "PETR4", "PRECO ATUAL": 28.5}]}

        WORKFLOW:
        1. Pass one exact ticker; use get_cotations for history instead
        2. Outside B3 market hours (10:00-17:30 BRT) returns the last closing price

        EXAMPLES:
        - Get live PETR4 price: search="PETR4"
        - Get live VALE3 price in compact form: search="VALE3", compact=true
        """
        result = queryLiveCotations(search)
        if compact:
            result = compressResponse(
                result, "get_live_price", {"search": search}, stocksCache.STOCKS_CACHE, stocksCache.nestedSample
            )
        return result

    return mcp
