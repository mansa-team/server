from types import SimpleNamespace

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


def _seed(client):
    client.post("/wallet/wallets", json={"name": "W"})
    client.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    )


def test_positions_math_with_live_price(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed(client)
    item = client.get("/wallet/positions").json()["items"][0]
    assert item["current_price"] == 30.0
    assert item["equity"] == 300.0
    # appreciation derives client-side: equity - qty*avg = 300 - 10*10.
    assert item["quantity"] == 10.0 and item["avgPrice"] == 10.0
    assert "appreciation" not in item and "percent_wallet" not in item and "buy_flag" not in item


def test_live_timeout_falls_back_to_null(dbSession, monkeypatch):
    def boom(*a, **k):
        raise requests.Timeout()

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=boom))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed(client)
    body = client.get("/wallet/positions").json()
    assert body["items"][0]["current_price"] is None
    assert body["equity_total"] == 0


def test_unknown_ticker_returns_null_not_422(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    resp = client.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "OUTROS",
            "ticker": "BTC",
            "date": "2026-01-10",
            "quantity": 1,
            "price": 100.0,
        },
    )
    assert resp.status_code == 201
    item = client.get("/wallet/positions").json()["items"][0]
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

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=fake_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed(client)
    item = client.get("/wallet/positions").json()["items"][0]
    assert item["current_price"] == 27.5
