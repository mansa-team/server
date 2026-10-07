"""Wallet tools ride only over MCP: registry leftover + dispatcher routing.

The legacy in-process wallet tools were deleted (spec 2026-10-07-wallet-mcp
step 5). TOOL_REGISTRY keeps the seven local tools; every wallet name is
absent on purpose, so dispatchToolCall routes it to the wallet MCP client
with the session JWT injected as a call argument. Auth boundary, cross-user
isolation and wrapper behavior live in tests/test_wallet_mcp.py.
"""

import importlib
import json
from types import SimpleNamespace

import pytest

from main.app.orunmila.tools import TOOL_REGISTRY, dispatchToolCall
from tests.test_wallet_mcp import _build_auth_app, _mcp_client, _seed_session_wallet
from tests.test_wallet_positions import _live_ok

LOCAL_TOOL_NAMES = {
    "search_memory",
    "save_memory",
    "execute_code",
    "read_file",
    "write_file",
    "list_files",
    "serve_file",
}

WALLET_TOOL_NAMES = {
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


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _fakeMcpClient(text='{"items": []}', isError=False):
    """Minimal stand-in for the wallet MCP client: records call args."""

    class FakeMcpClient:
        def __init__(self):
            self.calls = []
            self.session = SimpleNamespace(call_tool=self._record)

        async def _record(self, name, args):
            self.calls.append((name, args))
            return SimpleNamespace(isError=isError, content=[SimpleNamespace(text=text)])

    return FakeMcpClient()


def test_registry_holds_exactly_the_local_tools():
    assert set(TOOL_REGISTRY) == LOCAL_TOOL_NAMES
    assert len(TOOL_REGISTRY) == 7
    assert set(TOOL_REGISTRY) & WALLET_TOOL_NAMES == set()


def test_wallet_tools_module_is_deleted():
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("main.app.orunmila.tools.wallet")


class TestWalletToolRouting:
    """Wallet names are absent from the registry → they dispatch over MCP."""

    async def test_wallet_name_routes_to_wallet_client_with_bearer(self):
        functionCall = SimpleNamespace(name="wallet_positions", args={"group_by": "ticker"})
        assert functionCall.name not in TOOL_REGISTRY  # premise: no local wallet tool

        walletClient = _fakeMcpClient()
        stocksClient = _fakeMcpClient()

        result = await dispatchToolCall(
            functionCall, {"wallet": walletClient, "stocks": stocksClient}, rawToken="jwt-abc"
        )

        assert walletClient.calls == [("wallet_positions", {"group_by": "ticker", "authorization": "Bearer jwt-abc"})]
        assert stocksClient.calls == []
        assert result == {"result": '{"items": []}'}

    async def test_fallback_servers_never_get_authorization(self):
        functionCall = SimpleNamespace(name="wallet_summary", args={})
        failingWallet = _fakeMcpClient(isError=True)
        stocksClient = _fakeMcpClient()

        result = await dispatchToolCall(
            functionCall, {"wallet": failingWallet, "stocks": stocksClient}, rawToken="jwt-abc"
        )

        # Wallet-only: the bearer rides on the wallet server attempt; other
        # servers are tried without it (and only after the wallet errors).
        assert failingWallet.calls == [("wallet_summary", {"authorization": "Bearer jwt-abc"})]
        assert stocksClient.calls == [("wallet_summary", {})]
        assert result == {"result": '{"items": []}'}

    async def test_no_raw_token_leaves_args_untouched(self):
        functionCall = SimpleNamespace(name="wallet_rebalance", args={"ticker": "PETR4"})
        walletClient = _fakeMcpClient()

        await dispatchToolCall(functionCall, {"wallet": walletClient})

        assert walletClient.calls == [("wallet_rebalance", {"ticker": "PETR4"})]


class TestWalletDispatchEndToEnd:
    """dispatchToolCall → real in-process wallet MCP client → DB."""

    async def test_read_dispatch_round_trips_through_wallet_mcp(self, dbSession, monkeypatch):
        monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
        app = _build_auth_app(dbSession)
        token, _user, _wallet = _seed_session_wallet(dbSession)

        functionCall = SimpleNamespace(name="wallet_positions", args={})
        async with _mcp_client(app) as client:
            result = await dispatchToolCall(functionCall, {"wallet": client}, rawToken=token)

        payload = json.loads(result["result"])
        assert payload["items"][0]["ticker"] == "PETR4"
        assert payload["items"][0]["quantity"] == 10.0
        assert payload["equity_total"] == 300.0
