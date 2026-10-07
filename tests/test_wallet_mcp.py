"""Wallet MCP service tests: read-only tool scoping, middleware, mount wiring.

Tool surface is filtered by explicit operation IDs (WALLET_MCP_OPERATIONS) —
at this step exactly the 7 read routes; write routes must never leak into MCP.
"""

import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP

from main.controller.wallet_controller import router as walletRouter
from main.service.wallet_service import MCPDetectMiddleware, WALLET_MCP_OPERATIONS, WalletService

READ_TOOL_NAMES = {
    "wallet_positions",
    "wallet_rebalance",
    "wallet_summary",
    "wallet_allocation",
    "wallet_earnings",
    "wallet_performance",
    "wallet_progression_series",
}


def build_shared_app():
    """All service routers on one app — mimics production shared port."""
    from main.controller.authentication_controller import router as authRouter
    from main.controller.orunmila_controller import router as orunmilaRouter
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.controller.user_controller import router as userRouter

    app = FastAPI(title="Mansa Service 3200")
    for service_router in (authRouter, userRouter, orunmilaRouter, stocksRouter, walletRouter):
        app.include_router(service_router)
    return app


def make_wallet_mcp(app):
    """Create MCP matching production config (operation-ID allowlist)."""
    return FastApiMCP(
        app,
        name="Mansa Wallet MCP",
        include_operations=WALLET_MCP_OPERATIONS,
        headers=["authorization", "x-mcp"],
    )


class TestWalletMCPToolScoping:
    def test_mcp_exposes_exactly_seven_read_tools(self):
        mcp = make_wallet_mcp(build_shared_app())
        assert {t.name for t in mcp.tools} == READ_TOOL_NAMES
        assert len(mcp.tools) == 7

    def test_write_routes_excluded_from_mcp(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool_names = [t.name for t in mcp.tools]
        for forbidden in (
            "create_wallet",
            "list_wallets",
            "create_entry",
            "list_entries",
            "update_entry",
            "delete_entry",
            "set_rating",
            "cashflows",
            "dividends",
        ):
            assert not any(forbidden in name for name in tool_names)

    def test_no_other_service_routes_leak(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool_names = [t.name for t in mcp.tools]
        for forbidden in ("stocks", "auth", "orunmila", "register", "login", "logout"):
            assert not any(forbidden in name.lower() for name in tool_names)

    def test_descriptions_present(self):
        mcp = make_wallet_mcp(build_shared_app())
        for tool in mcp.tools:
            assert tool.description

    def test_mount_returns_valid_response(self):
        app = build_shared_app()
        mcp = make_wallet_mcp(app)
        mcp.mount_http(app, mount_path="/wallet/mcp")

        from fastapi.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/wallet/mcp")
            assert resp.status_code in (200, 405, 406)


class TestWalletMCPDetectMiddleware:
    async def run_through(self, scope):
        downstream = mock.AsyncMock()
        middleware = MCPDetectMiddleware(downstream)
        await middleware(scope, mock.Mock(), mock.Mock())
        return downstream

    async def test_mcp_header_injects_compact_query(self):
        scope = {"type": "http", "headers": [(b"x-mcp", b"true")], "query_string": b"", "state": {}}
        downstream = await self.run_through(scope)

        assert scope["state"]["compressed"] is True
        assert scope["query_string"] == b"compact=true"
        downstream.assert_awaited_once()

    async def test_mcp_header_existing_compact_not_duplicated(self):
        scope = {"type": "http", "headers": [(b"x-mcp", b"true")], "query_string": b"compact=false", "state": {}}
        await self.run_through(scope)

        assert scope["query_string"] == b"compact=false"

    async def test_plain_http_untouched(self):
        scope = {"type": "http", "headers": [(b"accept", b"application/json")], "query_string": b"a=1", "state": {}}
        await self.run_through(scope)

        assert "compressed" not in scope["state"]
        assert scope["query_string"] == b"a=1"


class TestWalletServiceInitialize:
    def test_initialize_wires_middleware_router_and_mount(self):
        app = FastAPI()
        with mock.patch("main.service.wallet_service.getApp", return_value=app) as mock_get_app:
            WalletService.initialize(39999)

        mock_get_app.assert_called_once_with(39999)

        # Wallet router registered
        assert any(getattr(route, "path", "").startswith("/wallet/") for route in app.routes)

        # Middleware stack
        middleware_names = [middleware.cls.__name__ for middleware in app.user_middleware]
        assert "MCPDetectMiddleware" in middleware_names

        # MCP mount registered
        assert any(getattr(route, "path", None) == "/wallet/mcp" for route in app.routes)
