"""Stocks FastMCP (/stocks/mcp2) scoping tests — Task 3 of the FastMCP replacement plan."""

EXPECTED_STOCKS_MCP2_TOOLS = {
    "list_fields",
    "get_historical",
    "get_fundamental",
    "get_cotations",
    "get_live_price",
}


async def test_stocks_mcp2_exposes_5():
    from main.service.stocksapi_service import buildStocksMCP

    tools = await buildStocksMCP().list_tools()
    assert {tool.name for tool in tools} == EXPECTED_STOCKS_MCP2_TOOLS
