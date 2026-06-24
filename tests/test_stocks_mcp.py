"""Tests for MCP tool scoping in stocksapi_service.py.

Verifies that FastApiMCP exposes exactly the 5 data query tools,
excluding health and generateKey endpoints.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from main.controller.stocksapi_controller import router as stocksRouter
from main.controller.authentication_controller import router as authRouter
from main.controller.user_controller import router as userRouter
from main.controller.prometheus_controller import router as prometheusRouter

# Production config: include_operations with correct full IDs
STOCKS_MCP_OPS = [
    "listFields_stocks_fields_get",
    "getHistorical_stocks_historical_get",
    "getFundamental_stocks_fundamental_get",
    "getCotations_stocks_cotations_get",
    "getLiveCotation_stocks_cotations_live_get",
]


def _build_app_with_all_routers():
    """Build a FastAPI app with all service routers — mimics production shared port."""
    app = FastAPI(title="Mansa Service 3200")
    app.include_router(authRouter)
    app.include_router(userRouter)
    app.include_router(prometheusRouter)
    app.include_router(stocksRouter)
    return app


def _make_mcp(app):
    """Create MCP matching production config."""
    return FastApiMCP(
        app,
        name="Mansa's Stocks API MCP",
        include_operations=STOCKS_MCP_OPS,
    )


class TestMCPToolScoping:
    """Verify FastApiMCP exposes exactly the 5 data query tools."""

    def test_mcp_exactly_five_tools(self):
        """MCP should expose exactly 5 tools: fields, historical, fundamental, cotations, live."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        assert len(mcp.tools) == 5

    def test_mcp_excludes_health(self):
        """Health endpoint should not be an MCP tool."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        tool_names = [t.name for t in mcp.tools]
        assert not any("health" in n for n in tool_names)

    def test_mcp_excludes_generate_key(self):
        """Key generation endpoint should not be an MCP tool."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        tool_names = [t.name for t in mcp.tools]
        assert not any("generate" in n for n in tool_names)

    def test_mcp_excludes_non_stocks_endpoints(self):
        """Auth, user, and prometheus tools should not appear."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        tool_names = [t.name for t in mcp.tools]
        for forbidden in ["register", "login", "prometheus", "logout"]:
            assert not any(forbidden in n.lower() for n in tool_names)

    def test_mcp_tool_names_match_endpoints(self):
        """Each MCP tool should correspond to a data endpoint."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        tool_names = [t.name.lower() for t in mcp.tools]
        for kw in ["fields", "historical", "fundamental", "cotations"]:
            assert any(kw in name for name in tool_names)

    def test_mcp_descriptions_are_meaningful(self):
        """Tool descriptions should be more than just the function name."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        for tool in mcp.tools:
            assert len(tool.description or "") > 50

    def test_mcp_mount_returns_valid_response(self):
        """MCP endpoint should respond — confirms mount is registered."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        mcp.mount_http(app, mount_path="/stocks/mcp")

        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/stocks/mcp")
            assert resp.status_code in (200, 405, 406)

    def test_wrong_operation_ids_match_nothing(self):
        """Short function names (the original bug) should match 0 tools."""
        app = _build_app_with_all_routers()
        mcp_broken = FastApiMCP(
            app,
            name="broken",
            include_operations=["getHistorical", "getFundamental"],
        )
        assert len(mcp_broken.tools) == 0

    def test_listfields_tool_exists(self):
        """The listFields discovery tool should be included."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        tool_names = [t.name for t in mcp.tools]
        assert any("listFields" in n or "list_fields" in n.lower() for n in tool_names)

    def test_listfields_description_mentions_discovery(self):
        """The listFields tool description should guide LLMs to call it first."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        listfields_tool = next((t for t in mcp.tools if "ield" in t.name.lower()), None)
        assert listfields_tool is not None
        desc = (listfields_tool.description or "").lower()
        assert "discover" in desc or "available" in desc or "first" in desc

    def test_historical_dates_format_in_description(self):
        """Historical tool description should mention YYYY date format."""
        app = _build_app_with_all_routers()
        mcp = _make_mcp(app)
        hist_tool = next((t for t in mcp.tools if "istorical" in t.name), None)
        assert hist_tool is not None
        desc = (hist_tool.description or "").lower()
        assert "yyyy" in desc
