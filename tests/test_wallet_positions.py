import pytest
import requests

import main.models.wallet  # noqa: F401
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _live_ok(url, params=None, headers=None, timeout=None):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"TICKER": "PETR4", "PRECO ATUAL": 30.0}]}

    assert params["search"] == "PETR4"
    return Resp()


def _seed(dbSession, client):
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    )
    return walletId


def test_positions_math_with_live_price(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(dbSession, client)
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    assert item["current_price"] == 30.0
    assert item["equity"] == 300.0
    assert item["appreciation"] == 200.0


def test_live_timeout_falls_back_to_null(dbSession, monkeypatch):
    def boom(*a, **k):
        raise requests.Timeout()

    monkeypatch.setattr(requests, "get", boom)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(dbSession, client)
    body = client.get(f"/wallet/positions?wallet_id={walletId}").json()
    assert body["items"][0]["current_price"] is None
    assert body["equity_total"] == 0


def test_unknown_ticker_returns_null_not_422(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    resp = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "OUTROS",
            "ticker": "BTC",
            "date": "2026-01-10",
            "quantity": 1,
            "price": 100.0,
        },
    )
    assert resp.status_code == 201
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    assert item["current_price"] is None


def test_cached_fallback_serves_when_live_fails(dbSession, monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        if url.endswith("/stocks/cotations/live"):
            raise requests.Timeout()

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": [{"DATA": "01-01-2026", "PRECO": 25.0}, {"DATA": "29-09-2026", "PRECO": 27.5}]}

        return Resp()

    monkeypatch.setattr(requests, "get", fake_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(dbSession, client)
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    assert item["current_price"] == 27.5
