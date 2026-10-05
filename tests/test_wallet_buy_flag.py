import asyncio
import hashlib

import pytest
import requests
from cashews import cache as cashewsCache

import main.models.wallet  # noqa: F401
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Holding
from tests.conftest import make_wallet_client
from tests.test_wallet_positions import _live_ok

RATINGS_ROUTE_DIGEST = "ab87ef76f6f3a61f652cf7fd0db94609d7d6dcb42169a81aa3e308ba8ca7f189"


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _live_two(url, params=None, headers=None, timeout=None):
    quotes = {"PETR4": 30.0, "VALE3": 10.0}

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"TICKER": params["search"], "PRECO ATUAL": quotes[params["search"]]}]}

    assert params["search"] in quotes
    return Resp()


def _seed_two(client, walletId):
    for ticker in ("PETR4", "VALE3"):
        client.post(
            "/wallet/entries",
            json={
                "wallet_id": walletId,
                "side": "Compra",
                "asset_type": "Stock",
                "ticker": ticker,
                "date": "2026-01-10",
                "quantity": 10,
                "price": 10.0,
            },
        )


def test_buy_flag_follows_delta_sign(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_two)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {ticker: 50.0 for ticker in tickers})
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    _seed_two(client, walletId)
    # Equities: PETR4 300, VALE3 100, total 400. Ratings 75/25 → targets 300/100 → flat.
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 75})
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "VALE3", "rating": 25})
    byTicker = {item["ticker"]: item for item in client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"]}
    assert byTicker["PETR4"]["buy_flag"] is False
    assert byTicker["VALE3"]["buy_flag"] is False
    # Re-rate VALE3 to 50 → targets PETR4 240 / VALE3 160 → sell PETR4, buy VALE3.
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "VALE3", "rating": 50})
    byTicker = {item["ticker"]: item for item in client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"]}
    assert byTicker["PETR4"]["buy_flag"] is False
    assert byTicker["VALE3"]["buy_flag"] is True


def test_zero_weights_all_hold(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_two)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {ticker: None for ticker in tickers})
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    _seed_two(client, walletId)
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 0})
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "VALE3", "rating": 0})
    body = client.get(f"/wallet/rebalance?wallet_id={walletId}").json()
    for item in body["items"]:
        assert item["delta_equity"] is None
        assert item["delta_qty"] is None
        assert item["side"] == "hold"
    for item in client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"]:
        assert item["buy_flag"] is False


def test_rebalance_weight_share_math(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_two)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {ticker: 50.0 for ticker in tickers})
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    _seed_two(client, walletId)
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 75})
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "VALE3", "rating": 50})
    body = client.get(f"/wallet/rebalance?wallet_id={walletId}").json()
    assert body["equity_total"] == pytest.approx(400.0)
    byTicker = {item["ticker"]: item for item in body["items"]}
    assert byTicker["PETR4"]["weight"] == 75
    assert byTicker["PETR4"]["target_pct"] == pytest.approx(0.6)
    assert byTicker["PETR4"]["current_pct"] == pytest.approx(0.75)
    assert byTicker["PETR4"]["delta_equity"] == pytest.approx(-60.0)
    assert byTicker["PETR4"]["delta_qty"] == pytest.approx(-2.0)
    assert byTicker["PETR4"]["side"] == "sell"
    assert byTicker["VALE3"]["weight"] == 50
    assert byTicker["VALE3"]["target_pct"] == pytest.approx(0.4)
    assert byTicker["VALE3"]["current_pct"] == pytest.approx(0.25)
    assert byTicker["VALE3"]["delta_equity"] == pytest.approx(60.0)
    assert byTicker["VALE3"]["delta_qty"] == pytest.approx(6.0)
    assert byTicker["VALE3"]["side"] == "buy"


def test_rebalance_deterministic(dbSession, monkeypatch):
    # Weight-share is a pure function of ratings + prices: same inputs → same outputs.
    monkeypatch.setattr(requests, "get", _live_two)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {ticker: 50.0 for ticker in tickers})
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    _seed_two(client, walletId)
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 75})
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "VALE3", "rating": 50})
    first = client.get(f"/wallet/rebalance?wallet_id={walletId}").json()
    second = client.get(f"/wallet/rebalance?wallet_id={walletId}").json()
    assert first == second
    assert sum(item["target_pct"] for item in first["items"]) == pytest.approx(1.0)
    assert sum(item["delta_equity"] for item in first["items"] if item["delta_equity"] is not None) == pytest.approx(
        0.0
    )


def test_new_holding_seeds_xango_score(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {"PETR4": 80.0})
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
    holding = dbSession.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == "PETR4").first()
    assert float(holding.rating) == pytest.approx(80.0)
    # Later entries never touch the rating: manual 42 survives another Compra.
    client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 42})
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "Stock",
            "ticker": "PETR4",
            "date": "2026-01-11",
            "quantity": 5,
            "price": 12.0,
        },
    )
    dbSession.expire_all()
    holding = dbSession.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == "PETR4").first()
    assert float(holding.rating) == pytest.approx(42.0)


def test_new_holding_defaults_ten_without_xango(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    monkeypatch.setattr(PositionsManager, "fetchXangoScores", lambda tickers: {"PETR4": None})
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
    holding = dbSession.query(Holding).filter(Holding.walletId == walletId, Holding.ticker == "PETR4").first()
    assert float(holding.rating) == pytest.approx(10.0)


def test_ratings_accept_zero_to_hundred(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
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
    assert client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 100}).json() == {
        "ticker": "PETR4",
        "rating": 100,
    }
    assert (
        client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 0}).status_code == 200
    )
    assert (
        client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 101}).status_code == 422
    )


def test_fetch_xango_scores_parses_fundamental(monkeypatch):

    def fundamental_ok(url, params=None, headers=None, timeout=None):
        assert url.endswith("/stocks/fundamental")
        assert params["search"] == "PETR4"
        assert params["fields"] == "XANGO INVESTING SCORE"

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": [{"TICKER": "PETR4", "XANGO INVESTING SCORE": 80.0}]}

        return Resp()

    def boom(url, params=None, headers=None, timeout=None):
        raise requests.Timeout()

    monkeypatch.setattr(requests, "get", fundamental_ok)
    assert PositionsManager.fetchXangoScores(("PETR4",)) == {"PETR4": 80.0}
    asyncio.run(cashewsCache.clear())
    monkeypatch.setattr(requests, "get", boom)
    assert PositionsManager.fetchXangoScores(("PETR4",)) == {"PETR4": None}


def test_ratings_route_untouched():
    raw = open("main/controller/wallet_controller.py", "rb").read().splitlines(keepends=True)[140:148]
    digest = hashlib.sha256(b"".join(raw)).hexdigest()
    assert digest == RATINGS_ROUTE_DIGEST  # any edit to set_rating_route fails loudly
