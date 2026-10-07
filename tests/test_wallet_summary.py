from types import SimpleNamespace

import pytest

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
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed(client)
    body = client.get("/wallet/summary").json()
    assert body == {
        "applied": 100.0,
        "equity": 300.0,
        "variation": 200.0,
        "first_date": "2026-01-10",
    }
    again = client.get("/wallet/summary").json()
    assert again["variation"] == 200.0
    from main.models.wallet import Snapshot

    assert dbSession.query(Snapshot).filter(Snapshot.walletId == walletId).count() == 1


def test_ratings_gate_and_positions_buy_flag(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed(client)
    assert client.put("/wallet/ratings", json={"ticker": "PETR4", "rating": 8}).json() == {
        "ticker": "PETR4",
        "rating": 8,
    }
    assert client.put("/wallet/ratings", json={"ticker": "PETR4", "rating": 100}).status_code == 200
    assert client.put("/wallet/ratings", json={"ticker": "PETR4", "rating": 101}).status_code == 422
    item = client.get("/wallet/positions").json()["items"][0]
    # Canonical raw: weight-share deltas derive client-side. Single holding owns
    # 100% of both weight and equity → client delta 0 → hold.
    # No manual targets remain: percent_ideal is None (display-only legacy column).
    assert item["percent_ideal"] is None and item["rating"] == 100
    assert item["equity"] == 300.0


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


def test_summary_returns_canonical_raw_no_twr(dbSession, monkeypatch):
    # TWR presets moved client-side: /summary returns no TWR keys; the windowed
    # TWR comes from /performance?from&to resolved by the client.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_twr_market_mock))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    assert (
        client.post(
            "/wallet/entries",
            json={
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
    body = client.get("/wallet/summary").json()
    assert body["applied"] == 400.0
    assert body["equity"] == 500.0
    assert body["variation"] == 100.0
    assert body["first_date"] == "2026-01-10"
    assert "profit_twr" not in body and "profit_twr_12m" not in body
    from datetime import date as dateType

    today = dateType.today().isoformat()
    perf = client.get(f"/wallet/performance?from=2026-01-01&to={today}").json()
    assert perf["twr"] == pytest.approx(0.25)
