from datetime import date

import pytest
import requests

import main.models.wallet  # noqa: F401
from main.models.wallet import Earning
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _jan_series(price_by_day):
    return [{"DATA": f"{day:02d}-01-2026", "PRECO": price_by_day.get(day, 10.0)} for day in range(1, 32)]


def _mock_get(url, params=None, headers=None, timeout=None):
    ticker = (params or {}).get("search", "PETR4")
    closes = {day: (10.0 if day <= 7 else 12.0) for day in range(1, 32)}

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"data": [{"TICKER": ticker, "COTACAO 10Y PADRAO": _jan_series(closes)}]}

    return Resp()


def _seed_wallet(client):
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-02",
            "quantity": 10,
            "price": 10.0,
        },
    )
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Venda",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-08",
            "quantity": 4,
            "price": 12.0,
        },
    )
    return walletId


def test_progression_daily_values(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    body = client.get(f"/wallet/progression?wallet_id={walletId}&from=2026-01-01&to=2026-01-10").json()
    assert body["granularity"] == "daily"
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-02"] == {"date": "2026-01-02", "equity": 100.0, "invested": 100.0}
    assert byDate["2026-01-07"] == {"date": "2026-01-07", "equity": 100.0, "invested": 100.0}
    assert byDate["2026-01-08"] == {"date": "2026-01-08", "equity": 72.0, "invested": 52.0}
    assert byDate["2026-01-10"] == {"date": "2026-01-10", "equity": 72.0, "invested": 52.0}
    assert "2026-01-01" not in byDate


def test_progression_weekly_monthly_and_auto(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    weekly = client.get(
        f"/wallet/progression?wallet_id={walletId}&from=2026-01-01&to=2026-01-31&granularity=weekly"
    ).json()
    assert weekly["granularity"] == "weekly"
    assert [point["date"] for point in weekly["points"]] == [
        "2026-01-04",
        "2026-01-11",
        "2026-01-18",
        "2026-01-25",
        "2026-01-31",
    ]
    assert weekly["points"][0]["equity"] == 100.0
    assert weekly["points"][1] == {"date": "2026-01-11", "equity": 72.0, "invested": 52.0}
    monthly = client.get(
        f"/wallet/progression?wallet_id={walletId}&from=2026-01-01&to=2026-01-31&granularity=monthly"
    ).json()
    assert [point["date"] for point in monthly["points"]] == ["2026-01-31"]
    assert monthly["points"][0]["equity"] == 72.0
    auto_short = client.get(f"/wallet/progression?wallet_id={walletId}&from=2026-01-01&to=2026-01-10").json()
    assert auto_short["granularity"] == "daily"
    auto_mid = client.get(f"/wallet/progression?wallet_id={walletId}&from=2025-01-01&to=2026-02-04").json()
    assert auto_mid["granularity"] == "weekly"
    auto_long = client.get(f"/wallet/progression?wallet_id={walletId}&from=2020-01-01&to=2026-02-04").json()
    assert auto_long["granularity"] == "monthly"


def test_cashflows_monthly(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    body = client.get(f"/wallet/cashflows?wallet_id={walletId}&from=2026-01-01&to=2026-02-28").json()
    assert body["months"] == [
        {"month": "2026-01", "in": 100.0, "out": 48.0, "net": 52.0},
        {"month": "2026-02", "in": 0.0, "out": 0.0, "net": 0.0},
    ]
    assert (body["total_in"], body["total_out"], body["net"]) == (100.0, 48.0, 52.0)


def test_dividends_monthly(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    dbSession.add(
        Earning(
            walletId=walletId,
            ticker="PETR4",
            kind="Div",
            exDate=date(2026, 1, 5),
            payDate=date(2026, 1, 15),
            gross=20.0,
            netIrAdjusted=20.0,
            status="Recebido",
        )
    )
    dbSession.add(
        Earning(
            walletId=walletId,
            ticker="PETR4",
            kind="JSCP",
            exDate=date(2026, 1, 20),
            payDate=date(2026, 2, 10),
            gross=10.0,
            netIrAdjusted=8.5,
            status="Recebido",
        )
    )
    dbSession.commit()
    body = client.get(f"/wallet/dividends/monthly?wallet_id={walletId}&from=2026-01-01&to=2026-02-28").json()
    assert body["months"] == [
        {"month": "2026-01", "gross": 20.0, "net": 20.0, "count": 1},
        {"month": "2026-02", "gross": 10.0, "net": 8.5, "count": 1},
    ]
    assert (body["total_gross"], body["total_net"], body["count"]) == (30.0, 28.5, 2)


def test_performance_metrics_filter(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    body = client.get(
        f"/wallet/performance?wallet_id={walletId}&from=2026-01-01&to=2026-01-11&metrics=twr,volatility"
    ).json()
    assert set(body) == {"twr", "volatility"}
    assert client.get(f"/wallet/performance?wallet_id={walletId}&metrics=bogus").status_code == 422


def test_performance_preset_ytd_matches_explicit(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _mock_get)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = _seed_wallet(client)
    explicit = client.get(f"/wallet/performance?wallet_id={walletId}&from=2026-01-01&to=2026-01-11").json()
    via_preset = client.get(f"/wallet/performance?wallet_id={walletId}&preset=YTD&to=2026-01-11").json()
    assert via_preset == explicit
    assert explicit["twr"] == pytest.approx(0.2)
    assert client.get(f"/wallet/performance?wallet_id={walletId}&preset=BOGUS").status_code == 422
