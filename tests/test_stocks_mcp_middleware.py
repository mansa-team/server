"""Tests for MCPDetectMiddleware and StocksAPIService.initialize in stocksapi_service.py.

Covers the ASGI middleware's compact-flag injection (x-mcp header -> compressed
state + compact=true query param) and the service bootstrap wiring (router,
middleware, MCP mount) without starting background schedulers.
"""

import asyncio
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI

from main.app.stocks_api.cache import stocksCache
from main.service.stocksapi_service import MCPDetectMiddleware, StocksAPIService


def _run_through(scope):
    """Run MCPDetectMiddleware over scope with a mocked async downstream app."""
    downstream = mock.AsyncMock()
    middleware = MCPDetectMiddleware(downstream)
    receive = mock.Mock()
    send = mock.Mock()
    asyncio.run(middleware(scope, receive, send))
    return downstream


class TestMCPDetectMiddleware:
    """MCPDetectMiddleware: x-mcp header forces compressed state + compact query."""

    def test_mcp_header_appends_compact_to_nonempty_query(self):
        scope = {"type": "http", "headers": [(b"x-mcp", b"true")], "query_string": b"a=1", "state": {}}
        downstream = _run_through(scope)

        assert scope["state"]["compressed"] is True
        assert scope["query_string"] == b"a=1&compact=true"
        downstream.assert_awaited_once()

    def test_mcp_header_with_empty_query_string(self):
        scope = {"type": "http", "headers": [(b"x-mcp", b"true")], "query_string": b""}
        assert "state" not in scope

        _run_through(scope)

        assert scope["state"]["compressed"] is True
        assert scope["query_string"] == b"compact=true"

    def test_mcp_header_existing_compact_not_duplicated(self):
        scope = {"type": "http", "headers": [(b"x-mcp", b"true")], "query_string": b"compact=false", "state": {}}

        _run_through(scope)

        assert scope["state"]["compressed"] is True
        assert scope["query_string"] == b"compact=false"

    def test_no_mcp_header_leaves_scope_untouched(self):
        scope = {"type": "http", "headers": [(b"user-agent", b"test")], "query_string": b"a=1", "state": {}}

        _run_through(scope)

        assert "compressed" not in scope["state"]
        assert scope["query_string"] == b"a=1"

    def test_non_http_scope_passes_through_untouched(self):
        scope = {"type": "websocket", "headers": [(b"x-mcp", b"true")], "query_string": b"a=1"}

        _run_through(scope)

        assert scope.get("state", {}).get("compressed") is None
        assert scope["query_string"] == b"a=1"


class TestStocksAPIServiceInitialize:
    """StocksAPIService.initialize: wires router, middleware and MCP mount."""

    def test_initialize_wires_router_middleware_and_mcp_mount(self):
        app = FastAPI()
        with (
            mock.patch("main.service.stocksapi_service.getApp", return_value=app) as mock_get_app,
            mock.patch.object(stocksCache, "cacheScheduler") as mock_scheduler,
        ):
            StocksAPIService.initialize(39999)

        mock_get_app.assert_called_once_with(39999)
        mock_scheduler.assert_called_once()

        # Stocks router registered
        assert any(getattr(r, "path", "").startswith("/stocks/") for r in app.routes)

        # Middleware stack
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "MCPDetectMiddleware" in middleware_names
        assert "GZipMiddleware" in middleware_names

        # MCP mount registered
        assert any(getattr(r, "path", None) == "/stocks/mcp" for r in app.routes)
