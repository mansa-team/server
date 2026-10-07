from datetime import date

import asyncio
import inspect

import pytest
import requests

import main.models.wallet  # noqa: F401
from main.app.orunmila.tools import TOOL_REGISTRY
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning
from tests.conftest import make_wallet_client

WALLET_TOOLS = [
    "wallet_positions",
    "wallet_summary",
    "wallet_allocation",
    "list_wallet_earnings",
    "wallet_performance",
    "wallet_rebalance",
]


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def test_wallet_tools_registered_and_read_only(dbSession):
    assert len(TOOL_REGISTRY) == 13
    for name in WALLET_TOOLS:
        assert name in TOOL_REGISTRY
    assert "narrate_positions" not in TOOL_REGISTRY
    for name in WALLET_TOOLS:
        source = inspect.getsource(TOOL_REGISTRY[name])
        for writer in ("addEntry", "updateEntry", "deleteEntry", "upsertTarget", "setRating", "syncEarnings"):
            assert writer not in source


def _seed_wallet(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-02",
            "quantity": 10,
            "price": 10.0,
        },
    )
    return walletId


def _live_ok(url, params=None, headers=None, timeout=None):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"TICKER": "PETR4", "PRECO ATUAL": 30.0}]}

    return Resp()


def _flat_series(url, params=None, headers=None, timeout=None):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            rows = [{"DATA": f"{day:02d}-01-2026", "PRECO": 10.0} for day in range(1, 10)]
            rows += [{"DATA": "10-01-2026", "PRECO": 10.0}, {"DATA": "11-01-2026", "PRECO": 11.0}]
            return {"data": rows}

    return Resp()


def _seed_earnings(dbSession, walletId):
    dbSession.add(
        Earning(
            walletId=walletId,
            ticker="PETR4",
            kind="Div",
            exDate=date(2026, 3, 1),
            payDate=date(2026, 4, 1),
            gross=10.0,
            netIrAdjusted=10.0,
            status="A Receber",
        )
    )
    dbSession.add(
        Earning(
            walletId=walletId,
            ticker="PETR4",
            kind="JSCP",
            exDate=date(2026, 3, 1),
            payDate=date(2026, 4, 1),
            gross=5.0,
            netIrAdjusted=4.25,
            status="Recebido",
        )
    )
    dbSession.commit()


def test_wallet_positions_returns_read_view(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    _seed_wallet(dbSession)
    result = asyncio.run(TOOL_REGISTRY["wallet_positions"](user={"userId": 1, "language": "pt-BR"}, db=dbSession))
    assert result["items"][0]["ticker"] == "PETR4"
    assert result["equity_total"] == 300.0


def test_wallet_summary_returns_totals(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    _seed_wallet(dbSession)
    result = asyncio.run(TOOL_REGISTRY["wallet_summary"](user={"userId": 1}, db=dbSession))
    assert result["applied"] == 100.0
    assert result["equity"] == 300.0
    assert result["variation"] == 200.0


def test_wallet_allocation_groups_by_ticker_and_asset(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    _seed_wallet(dbSession)
    byTicker = asyncio.run(TOOL_REGISTRY["wallet_allocation"](user={"userId": 1}, db=dbSession))
    assert byTicker["items"][0]["key"] == "PETR4"
    assert byTicker["equity_total"] == 300.0
    byAsset = asyncio.run(
        TOOL_REGISTRY["wallet_allocation"](group_by="assetType", user={"userId": 1}, db=dbSession)
    )
    assert byAsset["items"][0]["key"] == "ACOES"


def test_list_wallet_earnings_filters_by_status(dbSession, monkeypatch):
    walletId = _seed_wallet(dbSession)
    _seed_earnings(dbSession, walletId)
    # Stub market dividends so auto-sync only transitions statuses (no live accrual).
    monkeypatch.setattr(PositionsManager, "fetchMarketDividends", lambda ticker: [])
    # Auto-sync on read transitions past-payDate "A Receber" to "Recebido"
    # (seed payDate 2026-04-01 <= today), so the pending bucket is empty.
    pending = asyncio.run(TOOL_REGISTRY["list_wallet_earnings"](user={"userId": 1}, db=dbSession))
    assert pending["earnings"] == []
    received = asyncio.run(
        TOOL_REGISTRY["list_wallet_earnings"](status="Recebido", user={"userId": 1}, db=dbSession)
    )
    assert [row["kind"] for row in received["earnings"]] == ["Div", "JSCP"]
    assert received["earnings"][0]["gross"] == 10.0
    allRows = asyncio.run(TOOL_REGISTRY["list_wallet_earnings"](status=None, user={"userId": 1}, db=dbSession))
    assert len(allRows["earnings"]) == 2
    assert {row["status"] for row in allRows["earnings"]} == {"Recebido"}


def test_wallet_performance_returns_metrics(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _flat_series)
    walletId = _seed_wallet(dbSession)
    dbSession.add(
        Earning(
            walletId=walletId,
            ticker="PETR4",
            kind="Div",
            exDate=date(2026, 1, 5),
            payDate=date(2026, 2, 1),
            gross=10.0,
            netIrAdjusted=10.0,
            status="Recebido",
        )
    )
    dbSession.commit()
    result = asyncio.run(
        TOOL_REGISTRY["wallet_performance"](
            from_date="2026-01-01",
            to_date="2026-01-11",
            ticker="PETR4",
            user={"userId": 1},
            db=dbSession,
        )
    )
    assert result["twr"] == pytest.approx(0.21)
    assert result["dividends_received"] == 10.0


def test_wallet_performance_rejects_bad_date(dbSession):
    _seed_wallet(dbSession)
    result = asyncio.run(
        TOOL_REGISTRY["wallet_performance"](
            from_date="01/01/2026", to_date="2026-01-11", user={"userId": 1}, db=dbSession
        )
    )
    assert result == {"error": "invalid date, use YYYY-MM-DD"}


def test_wallet_rebalance_single_holding_holds(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    _seed_wallet(dbSession)
    result = asyncio.run(TOOL_REGISTRY["wallet_rebalance"](user={"userId": 1}, db=dbSession))
    # Canonical raw: single holding owns the whole weight share → client derives hold.
    assert len(result["items"]) == 1
    assert result["items"][0]["weight"] > 0
    assert result["items"][0]["equity"] == result["equity_total"]


def test_wallet_tools_cross_user_isolated(dbSession, monkeypatch):
    # Tools take no wallet id: user 2 only ever sees their own (empty)
    # wallet, never user 1's positions. Self-resolved ids can't be foreign,
    # so no per-call ownership check remains.
    import json

    monkeypatch.setattr(requests, "get", _live_ok)
    monkeypatch.setattr(PositionsManager, "fetchMarketDividends", lambda ticker: [])
    _seed_wallet(dbSession)
    baseArgs = {"user": {"userId": 2, "language": "pt-BR"}, "db": dbSession}
    for name in WALLET_TOOLS:
        args = dict(baseArgs)
        if name == "wallet_performance":
            args.update({"from_date": "2026-01-01", "to_date": "2026-01-11"})
        result = asyncio.run(TOOL_REGISTRY[name](**args))
        assert "PETR4" not in json.dumps(result, default=str)


def test_resolve_wallet_is_session_scoped(dbSession):
    # No wallet id is threaded anywhere: each user resolves to their OWN
    # wallet object. User 2 gets a fresh own wallet, never user 1's.
    from main.app.orunmila.tools.wallet import resolveWallet, resolveWalletId

    user1WalletId = _seed_wallet(dbSession)
    mine = resolveWallet(dbSession, 1)
    other = resolveWallet(dbSession, 2)
    assert int(mine.walletId) == user1WalletId
    assert int(mine.userId) == 1
    assert int(other.userId) == 2
    assert int(other.walletId) != user1WalletId
    assert resolveWalletId is resolveWallet


def test_wallet_tools_no_auth_no_data():
    baseArgs = {}
    for name in WALLET_TOOLS:
        args = dict(baseArgs)
        if name == "wallet_performance":
            args.update({"from_date": "2026-01-01", "to_date": "2026-01-11"})
        result = asyncio.run(TOOL_REGISTRY[name](**args))
        assert result == {"error": "Authentication required"}
