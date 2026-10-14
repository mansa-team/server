"""Stocks FastMCP (/stocks/mcp) scoping tests — Task 3 of the FastMCP replacement plan."""

EXPECTED_STOCKS_MCP_TOOLS = {
    "list_fields",
    "get_historical",
    "get_fundamental",
    "get_cotations",
    "get_live_price",
}


async def test_stocks_mcp_exposes_5():
    from main.controller.stocksapi_controller import mcp as stocksMcp

    tools = await stocksMcp.list_tools()
    assert {tool.name for tool in tools} == EXPECTED_STOCKS_MCP_TOOLS
