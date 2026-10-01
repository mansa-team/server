import asyncio
import inspect

import requests

from tests.conftest import make_wallet_client
from main.app.orunmila.tools import TOOL_REGISTRY


def test_narrate_positions_registered_and_read_only(dbSession):
    assert len(TOOL_REGISTRY) == 8
    assert "narrate_positions" in TOOL_REGISTRY
    source = inspect.getsource(TOOL_REGISTRY["narrate_positions"])
    for writer in ("addEntry", "updateEntry", "deleteEntry", "upsertTarget", "setRating", "syncEarnings"):
        assert writer not in source


def _seed_wallet(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "Stock",
            "ticker": "PETR4",
            "date": "2026-01-10",
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


def test_narrate_positions_returns_read_view(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    walletId = _seed_wallet(dbSession)
    result = asyncio.run(
        TOOL_REGISTRY["narrate_positions"](wallet_id=walletId, user={"userId": 1, "language": "pt-BR"}, db=dbSession)
    )
    assert result["wallet_id"] == walletId
    assert result["language"] == "pt-BR"
    assert result["positions"][0]["ticker"] == "PETR4"
    assert "summary" in result and "pending_earnings" in result


def test_narrate_positions_cross_user_denied(dbSession):
    walletId = _seed_wallet(dbSession)
    result = asyncio.run(
        TOOL_REGISTRY["narrate_positions"](wallet_id=walletId, user={"userId": 2, "language": "pt-BR"}, db=dbSession)
    )
    assert result == {"error": "not-owner"}


def test_narrate_positions_no_auth_no_data():
    result = asyncio.run(TOOL_REGISTRY["narrate_positions"](wallet_id=1))
    assert result == {"error": "Authentication required"}
