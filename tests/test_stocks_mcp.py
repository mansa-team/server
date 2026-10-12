"""Tests for MCP tool scoping in main/controller/stocksapi_controller.py.

Verifies that stocksMcp exposes exactly the 5 data query tools,
excluding health and generateKey endpoints.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient
from fastmcp import Client

from main.controller.stocksapi_controller import stocksMcp

EXPECTED_STOCKS_TOOLS = {
    "list_fields",
    "get_historical",
    "get_fundamental",
    "get_cotations",
    "get_live_price",
}


async def _stocks_tools():
    """Hand-written tool surface, exactly what /stocks/mcp serves."""
    async with Client(stocksMcp) as client:
        return await client.list_tools()


class TestMCPToolScoping:
    """Verify stocksMcp exposes exactly the 5 data query tools."""

    async def test_mcp_exactly_five_tools(self):
        """MCP should expose exactly 5 tools: fields, historical, fundamental, cotations, live."""
        tools = await _stocks_tools()
        assert {tool.name for tool in tools} == EXPECTED_STOCKS_TOOLS

    async def test_mcp_excludes_health(self):
        """Health endpoint should not be an MCP tool."""
        tool_names = [tool.name for tool in await _stocks_tools()]
        assert not any("health" in name for name in tool_names)

    async def test_mcp_excludes_generate_key(self):
        """Key generation endpoint should not be an MCP tool."""
        tool_names = [tool.name for tool in await _stocks_tools()]
        assert not any("generate" in name for name in tool_names)

    async def test_mcp_descriptions_are_meaningful(self):
        """Tool descriptions should be more than just the function name."""
        for tool in await _stocks_tools():
            assert len(tool.description or "") > 50

    def test_mcp_mount_returns_valid_response(self):
        """MCP endpoint should respond — confirms mount is registered."""
        app = FastAPI()
        mcpApp = stocksMcp.http_app(path="/", transport="streamable-http", stateless_http=True)
        app.mount("/stocks/mcp", mcpApp)

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/stocks/mcp")
            assert resp.status_code in (200, 405, 406)

    async def test_listfields_description_mentions_discovery(self):
        """The listFields tool description should guide LLMs to call it first."""
        tools = await _stocks_tools()
        listfields_tool = next((tool for tool in tools if "ield" in tool.name.lower()), None)
        assert listfields_tool is not None
        desc = (listfields_tool.description or "").lower()
        assert "discover" in desc or "available" in desc or "first" in desc

    async def test_historical_dates_format_in_description(self):
        """Historical tool description should mention YYYY date format."""
        tools = await _stocks_tools()
        hist_tool = next((tool for tool in tools if "istorical" in tool.name), None)
        assert hist_tool is not None
        desc = (hist_tool.description or "").lower()
        assert "yyyy" in desc
