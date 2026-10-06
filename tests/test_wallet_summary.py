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


def test_summary_math_and_snapshot_upsert(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(client)
    body = client.get(f"/wallet/summary?wallet_id={walletId}").json()
    assert body == {
        "applied": 100.0,
        "equity": 300.0,
        "variation": 200.0,
        "profit_twr": None,
        "profit_amount": 200.0,
        "profit_twr_12m": None,
        "profit_twr_12m_amount": 200.0,
    }
    again = client.get(f"/wallet/summary?wallet_id={walletId}").json()
    assert again["variation"] == 200.0
    from main.models.wallet import Snapshot

    assert dbSession.query(Snapshot).filter(Snapshot.walletId == walletId).count() == 1


def test_targets_drive_buy_flag_and_ratings_gate(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(client)
    assert (
        client.put(
            "/wallet/targets",
            json={"wallet_id": walletId, "key_kind": "ticker", "key_value": "PETR4", "percent_ideal": 80.0},
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/wallet/targets",
            json={"wallet_id": walletId, "key_kind": "ticker", "key_value": "PETR4", "percent_ideal": 101.0},
        ).status_code
        == 422
    )
    assert client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 8}).json() == {
        "ticker": "PETR4",
        "rating": 8,
    }
    assert (
        client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 100}).status_code == 200
    )
    assert (
        client.put("/wallet/ratings", json={"wallet_id": walletId, "ticker": "PETR4", "rating": 101}).status_code == 422
    )
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    # Weight-share: single holding owns 100% of both weight and equity → delta 0 → hold.
    assert item["percent_ideal"] == 80.0 and item["buy_flag"] is False


def _twr_market_mock(url, params=None, headers=None, timeout=None):
    from datetime import date, timedelta

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            if "cotations/live" in url:
                return {"data": [{"PRECO ATUAL": 50.0}]}
            if "cotations" in url:
                today = date.today()
                rows = []
                day = date(2026, 1, 1)
                while day <= today:
                    rows.append({"DATA": day.strftime("%d-%m-%Y"), "PRECO": 50.0 if day == today else 40.0})
                    day += timedelta(days=1)
                return {"data": [{"TICKER": "WEGE3", "COTACAO 10Y PADRAO": rows}]}
            return {"data": []}

    return Resp()


def test_summary_autoloads_twr(dbSession, monkeypatch):
    import pytest

    monkeypatch.setattr(requests, "get", _twr_market_mock)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    assert (
        client.post(
            "/wallet/entries",
            json={
                "wallet_id": walletId,
                "side": "Compra",
                "asset_type": "ACOES",
                "ticker": "WEGE3",
                "date": "2026-01-10",
                "quantity": 10,
                "price": 40.0,
            },
        ).status_code
        == 201
    )
    body = client.get(f"/wallet/summary?wallet_id={walletId}").json()
    assert body["applied"] == 400.0
    assert body["equity"] == 500.0
    assert body["profit_twr"] == pytest.approx(0.25)
    assert body["profit_twr_12m"] == pytest.approx(0.25)
