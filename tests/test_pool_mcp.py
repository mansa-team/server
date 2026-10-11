"""Orunmila pool → FastMCP /mcp endpoints — Task 5 of the FastMCP replacement plan.

Proves the pool's buildClient talks to the /mcp mounts over Streamable HTTP
(httpx2 ASGI factory in-process, FastMCP 4.1 API only): wallet/mcp lists the
exact 11 tools, and dispatchToolCall still injects the session JWT as a
first-class `authorization` tool arg for wallet only (no header-pop reliance).
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx2
import pytest
from fastapi import FastAPI

from main.app.authentication.util import createAccessToken
from main.app.orunmila.mcp import MCP_SERVERS, buildClient
from main.app.orunmila.tools import dispatchToolCall

EXPECTED_WALLET_MCP_TOOLS = {
    "wallet_positions",
    "wallet_rebalance",
    "wallet_summary",
    "wallet_allocation",
    "wallet_earnings",
    "wallet_performance",
    "wallet_progression_series",
    "record_entry",
    "set_rating",
    "explain_twr",
    "wallet_progression",
}


def _asgiFactory(app):
    def asgiFactory(**kwargs):
        clientArgs = {
            key: value for key, value in kwargs.items() if key in ("headers", "auth", "follow_redirects", "timeout")
        }
        return httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://apiserver", **clientArgs)

    return asgiFactory


async def test_pool_lists_mcp_tools():
    urls = {server["name"]: server["url"] for server in MCP_SERVERS}
    assert urls["wallet"].endswith("/wallet/mcp")
    assert urls["stocks"].endswith("/stocks/mcp")

    from main.controller.wallet_controller import walletMcp

    mcpServer = walletMcp
    mcpApp = mcpServer.http_app(path="/", transport="streamable-http", stateless_http=True)
    app = FastAPI()
    app.mount("/wallet/mcp", mcpApp)

    # Transport-level JWTVerifier gate: pool connections carry a Bearer session
    # JWT as the HTTP Authorization header (per-tool identity still rides the
    # `authorization` tool arg injected by dispatchToolCall).
    token = createAccessToken({"userId": "1", "sessionId": "pool-probe"})
    server = {
        "name": "wallet",
        "url": "http://apiserver/wallet/mcp",
        "headers": {"Authorization": f"Bearer {token}"},
    }
    async with mcpApp.lifespan(app):
        client = buildClient(server, httpx_client_factory=_asgiFactory(app))
        async with client:
            tools = await client.list_tools()
    assert {tool.name for tool in tools} == EXPECTED_WALLET_MCP_TOOLS


def _toolTextResult(text):
    return SimpleNamespace(is_error=False, content=[SimpleNamespace(text=text)])


def _errorResult():
    return SimpleNamespace(is_error=True, content=[])


async def test_dispatch_injects_bearer_wallet_only():
    """Mirrors test_wallet_mcp.py TestDispatcherAuthInjection on the /mcp path."""
    functionCall = MagicMock()
    functionCall.name = "wallet_positions"
    functionCall.args = {"group_by": "ticker"}
    walletClient = MagicMock()
    walletClient.session.call_tool = AsyncMock(return_value=_toolTextResult('{"items": []}'))

    result = await dispatchToolCall(functionCall, {"wallet": walletClient}, user={"userId": 1}, rawToken="jwt-abc")

    walletClient.session.call_tool.assert_awaited_once_with(
        "wallet_positions", {"group_by": "ticker", "authorization": "Bearer jwt-abc"}
    )
    assert result == {"result": '{"items": []}'}


async def test_dispatch_leaves_non_wallet_args_untouched():
    functionCall = MagicMock()
    functionCall.name = "search"
    functionCall.args = {"query": "news"}
    stocksClient = MagicMock()
    stocksClient.session.call_tool = AsyncMock(return_value=_errorResult())
    searxngClient = MagicMock()
    searxngClient.session.call_tool = AsyncMock(return_value=_toolTextResult("results"))

    await dispatchToolCall(functionCall, {"stocks": stocksClient, "searxng": searxngClient}, rawToken="jwt-abc")

    stocksClient.session.call_tool.assert_awaited_once_with("search", {"query": "news"})
    searxngClient.session.call_tool.assert_awaited_once_with("search", {"query": "news"})


async def test_pool_lists_tools_with_service_token_only(monkeypatch):
    """R2: pool transport carries only X-Service-Token (no user JWT) and still lists."""
    from main.app.authentication import util as authUtil

    monkeypatch.setattr(authUtil, "verifyServiceToken", lambda db, token: token == "svc-probe")

    from main.controller.wallet_controller import walletMcp

    mcpServer = walletMcp
    mcpApp = mcpServer.http_app(path="/", transport="streamable-http", stateless_http=True)
    app = FastAPI()
    app.mount("/wallet/mcp", mcpApp)

    server = {
        "name": "wallet",
        "url": "http://apiserver/wallet/mcp",
        "headers": {"X-Service-Token": "svc-probe"},
    }
    async with mcpApp.lifespan(app):
        client = buildClient(server, httpx_client_factory=_asgiFactory(app))
        async with client:
            tools = await client.list_tools()
    assert {tool.name for tool in tools} == EXPECTED_WALLET_MCP_TOOLS


async def test_pool_rejects_forged_service_token(monkeypatch):
    """R2: forged X-Service-Token still fails at the transport gate (no silent pass)."""
    from main.app.authentication import util as authUtil

    monkeypatch.setattr(authUtil, "verifyServiceToken", lambda db, token: False)

    from main.controller.wallet_controller import walletMcp

    mcpServer = walletMcp
    mcpApp = mcpServer.http_app(path="/", transport="streamable-http", stateless_http=True)
    app = FastAPI()
    app.mount("/wallet/mcp", mcpApp)

    server = {
        "name": "wallet",
        "url": "http://apiserver/wallet/mcp",
        "headers": {"X-Service-Token": "forged-service-token"},
    }
    with pytest.raises(Exception):
        async with mcpApp.lifespan(app):
            client = buildClient(server, httpx_client_factory=_asgiFactory(app))
            async with client:
                await client.list_tools()
