"""Wallet MCP tests: tool scoping, middleware, mount wiring, JWT auth boundary.

Tool surface is filtered by explicit operation IDs (WALLET_MCP_OPERATIONS) —
seven read routes plus four LLM-shaped wrappers; unwrapped writes must never
leak into MCP. Auth rides as a call argument (the shared MCP pool freezes
transport headers): the dispatcher injects `authorization`, FastApiMCP pops it
into the replayed request headers, and getCurrentUser verifies it there.
"""

import json
import os
import sys
from datetime import date
from unittest import mock
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi_mcp import FastApiMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastmcp import Client
from fastmcp.client.client import StreamableHttpTransport

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

WRAPPER_TOOL_NAMES = {
    "record_entry",
    "set_rating",
    "explain_twr",
    "wallet_progression",
}

EXPECTED_TOOL_NAMES = READ_TOOL_NAMES | WRAPPER_TOOL_NAMES


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


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
    def test_mcp_exposes_exact_tool_surface(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool_names = {t.name for t in mcp.tools}
        assert tool_names == EXPECTED_TOOL_NAMES
        assert len(mcp.tools) == 11
        assert WRAPPER_TOOL_NAMES <= tool_names
        assert READ_TOOL_NAMES <= tool_names

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
            "ratings",
            "cashflows",
            "dividends",
        ):
            assert not any(forbidden in name for name in tool_names)

    def test_no_other_service_routes_leak(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool_names = [t.name for t in mcp.tools]
        for forbidden in ("stocks", "auth", "orunmila", "register", "login", "logout"):
            assert not any(forbidden in name.lower() for name in tool_names)

    def test_all_tools_have_anthropic_docstrings(self):
        mcp = make_wallet_mcp(build_shared_app())
        assert len(mcp.tools) == 11
        for tool in mcp.tools:
            assert tool.description
            for section in ("PARAMETERS:", "RESPONSE format:", "WORKFLOW:", "EXAMPLES:"):
                assert section in tool.description, f"{tool.name} missing {section}"

    def test_record_entry_schema_is_flat_body(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool = next(t for t in mcp.tools if t.name == "record_entry")
        properties = tool.inputSchema.get("properties", {})
        assert set(properties) == {"side", "asset_type", "ticker", "date", "quantity", "price", "costs"}
        assert tool.inputSchema["required"] == ["side", "asset_type", "ticker", "date", "quantity", "price"]
        assert properties["side"]["enum"] == ["Compra", "Venda"]
        assert properties["asset_type"]["enum"] == ["ACOES", "OUTROS"]

    def test_wallet_progression_schema_bounds(self):
        mcp = make_wallet_mcp(build_shared_app())
        tool = next(t for t in mcp.tools if t.name == "wallet_progression")
        props = tool.inputSchema["properties"]
        assert props["max_points"]["minimum"] == 2
        assert props["max_points"]["maximum"] == 2000

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


def _make_wallet(dbSession):
    """Real user + auto-created wallet (mirrors the session chain used by routes)."""
    from main.app.wallet.wallets import WalletsManager
    from main.models.user import User

    user = User(username="wrapuser", email="wrap@example.com", passwordHash="h", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    wallet = WalletsManager.getMyWallet(dbSession, user.userId)
    return user, wallet


class TestWalletWrapperBehavior:
    """Direct-call tests for the four MCP wrappers (no ASGI round trip)."""

    def test_record_entry_coerces_date_and_serializes_holding(self, dbSession):
        from main.controller.wallet_controller import record_entry_route

        user, wallet = _make_wallet(dbSession)
        result = record_entry_route(
            side="Compra",
            asset_type="ACOES",
            ticker="PETR4",
            date="2026-01-05",
            quantity=10.0,
            price=25.0,
            costs=1.0,
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result["entryId"] is not None
        assert result["holding"] == {"ticker": "PETR4", "quantity": 10.0, "avgPrice": 25.1}

    def test_record_entry_rejects_bad_date(self, dbSession):
        from main.controller.wallet_controller import record_entry_route

        user, wallet = _make_wallet(dbSession)
        with pytest.raises(HTTPException) as excinfo:
            record_entry_route(
                side="Compra",
                asset_type="ACOES",
                ticker="PETR4",
                date="05/01/2026",
                quantity=10.0,
                price=25.0,
                costs=0.0,
                authorization=None,
                currentUser={"userId": str(user.userId)},
                wallet=wallet,
                db=dbSession,
            )

        assert excinfo.value.status_code == 422

    def test_set_rating_wrapper_updates_single_rating(self, dbSession):
        from main.app.wallet.entries import EntryCreate, EntriesManager
        from main.controller.wallet_controller import set_rating_wrapper_route

        user, wallet = _make_wallet(dbSession)
        EntriesManager.addEntry(
            dbSession,
            wallet,
            EntryCreate(
                side="Compra", asset_type="ACOES", ticker="PETR4", date=date(2026, 1, 5), quantity=10, price=25.0
            ),
        )

        result = set_rating_wrapper_route(
            ticker="PETR4",
            rating=80.0,
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result == {"ticker": "PETR4", "rating": 80.0}

    def test_set_rating_wrapper_404_when_not_held(self, dbSession):
        from main.controller.wallet_controller import set_rating_wrapper_route

        user, wallet = _make_wallet(dbSession)
        with pytest.raises(HTTPException) as excinfo:
            set_rating_wrapper_route(
                ticker="VALE3",
                rating=50.0,
                authorization=None,
                currentUser={"userId": str(user.userId)},
                wallet=wallet,
                db=dbSession,
            )

        assert excinfo.value.status_code == 404

    def test_explain_twr_gloss_leg_and_per_ticker(self, dbSession, monkeypatch):
        from main.app.wallet.entries import EntryCreate, EntriesManager
        from main.app.wallet.performance import PerformanceManager
        from main.controller.wallet_controller import explain_twr_route

        user, wallet = _make_wallet(dbSession)
        EntriesManager.addEntry(
            dbSession,
            wallet,
            EntryCreate(
                side="Compra", asset_type="ACOES", ticker="PETR4", date=date(2026, 1, 5), quantity=10, price=25.0
            ),
        )

        fakePerf = {
            "twr": 0.10,
            "twr_annualized": 0.22,
            "volatility": 0.15,
            "dividends_received": 12.5,
            "price_return": 0.08,
        }
        monkeypatch.setattr(
            PerformanceManager,
            "getPerformance",
            classmethod(lambda cls, db, wallet, ticker, start, end: dict(fakePerf)),
        )

        result = explain_twr_route(
            ticker=None,
            from_date="2026-01-01",
            to_date="2026-06-30",
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result["from"] == "2026-01-01"
        assert result["to"] == "2026-06-30"
        assert result["twr"] == 0.10
        assert result["dividend_leg"] == pytest.approx(0.02)
        assert result["tickers"] == [{"ticker": "PETR4", "twr": 0.10}]
        assert result["worst_tickers"] == [{"ticker": "PETR4", "twr": 0.10}]
        assert "TWR 0.1000" in result["gloss"]

    def test_explain_twr_ticker_scoped_skips_universe(self, dbSession, monkeypatch):
        from main.app.wallet.performance import PerformanceManager
        from main.controller.wallet_controller import explain_twr_route

        user, wallet = _make_wallet(dbSession)
        fakePerf = {
            "twr": -0.04,
            "twr_annualized": -0.1,
            "volatility": 0.3,
            "dividends_received": 0.0,
            "price_return": -0.04,
        }
        monkeypatch.setattr(
            PerformanceManager,
            "getPerformance",
            classmethod(lambda cls, db, wallet, ticker, start, end: dict(fakePerf)),
        )

        result = explain_twr_route(
            ticker="VALE3",
            from_date="2026-01-01",
            to_date="2026-06-30",
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result["ticker"] == "VALE3"
        assert result["tickers"] == [{"ticker": "VALE3", "twr": -0.04}]
        assert result["dividend_leg"] == 0.0

    def test_wallet_progression_downsamples_with_stride(self, dbSession, monkeypatch):
        from main.app.wallet.analytics import AnalyticsManager
        from main.controller.wallet_controller import wallet_progression_route

        user, wallet = _make_wallet(dbSession)

        def makeSeries(count):
            return {
                "granularity": "daily",
                "from": "2026-01-01",
                "to": "2026-01-31",
                "points": [{"date": f"d{index}", "equity": float(index), "invested": 1.0} for index in range(count)],
            }

        monkeypatch.setattr(
            AnalyticsManager, "getProgression", classmethod(lambda cls, db, wallet, start, end: makeSeries(10))
        )

        result = wallet_progression_route(
            from_date="2026-01-01",
            to_date="2026-01-31",
            max_points=4,
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result["count"] == 10
        assert result["stride"] == 3
        assert [point["date"] for point in result["points"]] == ["d0", "d3", "d6", "d9"]
        assert result["returned"] == 4

    def test_wallet_progression_always_keeps_last_point(self, dbSession, monkeypatch):
        from main.app.wallet.analytics import AnalyticsManager
        from main.controller.wallet_controller import wallet_progression_route

        user, wallet = _make_wallet(dbSession)
        monkeypatch.setattr(
            AnalyticsManager,
            "getProgression",
            classmethod(
                lambda cls, db, wallet, start, end: {
                    "granularity": "daily",
                    "from": "2026-01-01",
                    "to": "2026-01-31",
                    "points": [{"date": f"d{index}", "equity": float(index), "invested": 1.0} for index in range(11)],
                }
            ),
        )

        result = wallet_progression_route(
            from_date="2026-01-01",
            to_date="2026-01-31",
            max_points=4,
            authorization=None,
            currentUser={"userId": str(user.userId)},
            wallet=wallet,
            db=dbSession,
        )

        assert result["stride"] == 3
        assert [point["date"] for point in result["points"]] == ["d0", "d3", "d6", "d9", "d10"]


def _toolTextResult(text):
    block = MagicMock()
    block.text = text
    result = MagicMock()
    result.isError = False
    result.content = [block]
    return result


def _errorResult():
    result = MagicMock()
    result.isError = True
    result.content = []
    return result


class TestDispatcherAuthInjection:
    """dispatchToolCall must inject the session JWT as an argument for wallet only."""

    async def test_wallet_call_gets_bearer_token(self):
        from main.app.orunmila.tools import dispatchToolCall

        functionCall = MagicMock()
        functionCall.name = "wallet_progression_series"
        functionCall.args = {}
        walletClient = MagicMock()
        walletClient.session.call_tool = AsyncMock(return_value=_toolTextResult('{"items": []}'))

        result = await dispatchToolCall(functionCall, {"wallet": walletClient}, user={"userId": 1}, rawToken="jwt-abc")

        walletClient.session.call_tool.assert_awaited_once_with(
            "wallet_progression_series", {"authorization": "Bearer jwt-abc"}
        )
        assert result == {"result": '{"items": []}'}

    async def test_other_mcp_clients_do_not_get_token(self):
        from main.app.orunmila.tools import dispatchToolCall

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

    async def test_no_raw_token_leaves_args_untouched(self):
        from main.app.orunmila.tools import dispatchToolCall

        functionCall = MagicMock()
        functionCall.name = "wallet_progression_series"
        functionCall.args = {}
        walletClient = MagicMock()
        walletClient.session.call_tool = AsyncMock(return_value=_toolTextResult("{}"))

        await dispatchToolCall(functionCall, {"wallet": walletClient})

        walletClient.session.call_tool.assert_awaited_once_with("wallet_progression_series", {})


class TestRawTokenThreading:
    """streamMessage must thread the raw token down to dispatchToolCall."""

    @patch("main.app.orunmila.agent.dispatchToolCall")
    @patch("main.app.orunmila.agent.OrunmilaChatManager")
    @patch("main.app.orunmila.agent.Config")
    @patch("main.app.orunmila.agent.genai")
    @patch("main.app.orunmila.agent.clientPool")
    async def test_raw_token_reaches_dispatch(self, mock_pool, mock_genai, mock_config, mock_chat, mock_dispatch):
        mock_config.ORUNMILA = MagicMock(GEMINI_API_KEY="test-key")
        mock_config.DEBUG_MODE = True
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}
        mock_chat.getHistory.return_value = []
        mock_pool.getClients = AsyncMock(return_value=({"wallet": MagicMock()}, [MagicMock()]))

        class FakeFunctionCall:
            name = "wallet_progression_series"
            args = {}

        class FakeChunk:
            def __init__(self, text=None, function_calls=None):
                self.text = text
                self.function_calls = function_calls

        call_count = 0

        async def fake_stream(msg):
            nonlocal call_count
            call_count += 1
            if call_count == 1:

                async def first():
                    yield FakeChunk(function_calls=[FakeFunctionCall()])

                return first()

            async def second():
                yield FakeChunk(text="done")

            return second()

        mock_chat_session = MagicMock()
        mock_chat_session.send_message_stream = AsyncMock(side_effect=fake_stream)
        mock_dispatch.return_value = {"result": "ok"}

        from main.app.orunmila.agent import Orunmila

        gen = Orunmila()
        gen.makeChat = MagicMock(return_value=mock_chat_session)

        events = []
        async for event in gen.streamMessage(query="oi", sessionId="s-token", db=MagicMock(), rawToken="jwt-xyz"):
            events.append(event)

        mock_dispatch.assert_awaited_once()
        assert mock_dispatch.await_args.kwargs["rawToken"] == "jwt-xyz"


def _build_auth_app(dbSession):
    from config import getSession
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    registerErrorHandlers(app)
    app.include_router(walletRouter)
    app.add_middleware(MCPDetectMiddleware)

    mcp = FastApiMCP(
        app,
        name="Mansa Wallet MCP",
        include_operations=WALLET_MCP_OPERATIONS,
        headers=["authorization", "x-mcp"],
    )
    mcp.mount_http(app, mount_path="/wallet/mcp")

    app.dependency_overrides[getSession] = lambda: dbSession
    return app


def _seed_session_token(dbSession):
    """Real user + session rows and a signed session JWT (production auth chain)."""
    from main.app.authentication.session import SessionManager
    from main.app.authentication.util import createAccessToken
    from main.models.user import User

    user = User(username="mcpuser", email="mcpuser@example.com", passwordHash="hash", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    return createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})


def _mcp_client(app):
    def asgiFactory(**kwargs):
        clientArgs = {
            key: value for key, value in kwargs.items() if key in ("headers", "auth", "follow_redirects", "timeout")
        }
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://apiserver", **clientArgs)

    transport = StreamableHttpTransport(
        url="http://apiserver/wallet/mcp",
        headers={"X-MCP": "true"},
        httpx_client_factory=asgiFactory,
    )
    return Client(transport=transport)


class TestWalletMCPAuthBoundary:
    """End-to-end in-process MCP round trip through the replayed ASGI request."""

    async def test_call_without_token_is_rejected(self, dbSession):
        app = _build_auth_app(dbSession)
        async with _mcp_client(app) as client:
            result = await client.call_tool("wallet_positions", {}, raise_on_error=False)

        assert result.is_error
        assert "401" in result.content[0].text

    async def test_call_with_valid_session_jwt_succeeds(self, dbSession):
        app = _build_auth_app(dbSession)
        token = _seed_session_token(dbSession)

        async with _mcp_client(app) as client:
            result = await client.call_tool(
                "wallet_positions", {"authorization": f"Bearer {token}"}, raise_on_error=False
            )

        assert not result.is_error
        assert json.loads(result.content[0].text) == {"items": [], "equity_total": 0.0}

    async def test_valid_jwt_scoped_to_its_user(self, dbSession):
        app = _build_auth_app(dbSession)
        token = _seed_session_token(dbSession)

        async with _mcp_client(app) as client:
            result = await client.call_tool(
                "wallet_summary", {"authorization": f"Bearer {token}"}, raise_on_error=False
            )

        assert not result.is_error
        payload = json.loads(result.content[0].text)
        assert payload["applied"] == 0.0
        assert payload["first_date"] is None

    async def test_wrapper_call_without_token_is_rejected(self, dbSession):
        app = _build_auth_app(dbSession)
        async with _mcp_client(app) as client:
            result = await client.call_tool(
                "wallet_progression", {"from_date": "2026-01-01", "to_date": "2026-02-01"}, raise_on_error=False
            )

        assert result.is_error
        assert "401" in result.content[0].text

    async def test_record_entry_with_session_jwt_roundtrips(self, dbSession):
        """Full write path over MCP: JWT argument → header pop → ledger write."""
        app = _build_auth_app(dbSession)
        token = _seed_session_token(dbSession)

        async with _mcp_client(app) as client:
            result = await client.call_tool(
                "record_entry",
                {
                    "side": "Compra",
                    "asset_type": "ACOES",
                    "ticker": "PETR4",
                    "date": "2026-01-05",
                    "quantity": 10,
                    "price": 25.0,
                    "costs": 1.0,
                    "authorization": f"Bearer {token}",
                },
                raise_on_error=False,
            )

        assert not result.is_error
        payload = json.loads(result.content[0].text)
        assert payload["entryId"] is not None
        assert payload["holding"] == {"ticker": "PETR4", "quantity": 10.0, "avgPrice": 25.1}

    async def test_record_entry_via_mcp_without_token_writes_nothing(self, dbSession):
        from main.models.wallet import Transaction

        app = _build_auth_app(dbSession)
        async with _mcp_client(app) as client:
            result = await client.call_tool(
                "record_entry",
                {
                    "side": "Compra",
                    "asset_type": "ACOES",
                    "ticker": "PETR4",
                    "date": "2026-01-05",
                    "quantity": 10,
                    "price": 25.0,
                },
                raise_on_error=False,
            )

        assert result.is_error
        assert "401" in result.content[0].text
        assert dbSession.query(Transaction).count() == 0


class TestWalletMCPParams:
    """authorization rides on the operation (pop target) but stays off the tool schema."""

    def test_authorization_declared_on_operation_not_in_schema(self):
        mcp = make_wallet_mcp(build_shared_app())
        params = mcp.operation_map["wallet_positions"]["parameters"]
        assert any(p.get("name") == "authorization" and p.get("in") == "header" for p in params)

        # Hidden from the LLM-facing schema: only the dispatcher supplies it.
        readTool = next(t for t in mcp.tools if t.name == "wallet_positions")
        assert "authorization" not in readTool.inputSchema.get("properties", {})
