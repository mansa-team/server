from datetime import date
from types import SimpleNamespace

import pytest
from cashews import cache as cashewsCache

import main.models.wallet  # noqa: F401
from main.app.wallet.analytics import AnalyticsManager
from main.models.wallet import Earning
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
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
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed_wallet(client)
    body = client.get("/wallet/progression?from=2026-01-01&to=2026-01-10").json()
    assert body["granularity"] == "daily"
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-02"] == {"date": "2026-01-02", "equity": 100.0, "invested": 100.0}
    assert byDate["2026-01-07"] == {"date": "2026-01-07", "equity": 100.0, "invested": 100.0}
    assert byDate["2026-01-08"] == {"date": "2026-01-08", "equity": 72.0, "invested": 60.0}
    assert byDate["2026-01-10"] == {"date": "2026-01-10", "equity": 72.0, "invested": 60.0}
    assert "2026-01-01" not in byDate


def test_progression_is_canonical_daily(dbSession, monkeypatch):
    # Bucketing moved client-side: server always returns every daily point,
    # granularity is always "daily" regardless of window span.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed_wallet(client)
    body = client.get("/wallet/progression?from=2026-01-01&to=2026-01-31").json()
    assert body["granularity"] == "daily"
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-02"] == {"date": "2026-01-02", "equity": 100.0, "invested": 100.0}
    assert byDate["2026-01-08"] == {"date": "2026-01-08", "equity": 72.0, "invested": 60.0}
    assert byDate["2026-01-31"] == {"date": "2026-01-31", "equity": 72.0, "invested": 60.0}
    assert "2026-01-01" not in byDate
    longBody = client.get("/wallet/progression?from=2020-01-01&to=2026-02-04").json()
    assert longBody["granularity"] == "daily"


def test_cashflows_returns_raw_rows(dbSession, monkeypatch):
    # Month buckets + rounding + totals moved client-side: server returns
    # windowed ledger rows with per-row in/out legs.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed_wallet(client)
    body = client.get("/wallet/cashflows?from=2026-01-01&to=2026-02-28").json()
    assert (body["from"], body["to"]) == ("2026-01-01", "2026-02-28")
    assert body["rows"] == [
        {
            "date": "2026-01-02",
            "side": "Compra",
            "ticker": "PETR4",
            "quantity": 10.0,
            "price": 10.0,
            "costs": 0.0,
            "in": 100.0,
            "out": 0.0,
        },
        {
            "date": "2026-01-08",
            "side": "Venda",
            "ticker": "PETR4",
            "quantity": 4.0,
            "price": 12.0,
            "costs": 0.0,
            "in": 0.0,
            "out": 48.0,
        },
    ]


def test_dividends_monthly(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
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
    body = client.get("/wallet/dividends/monthly?from=2026-01-01&to=2026-02-28").json()
    assert (body["from"], body["to"]) == ("2026-01-01", "2026-02-28")
    assert body["rows"] == [
        {"pay_date": "2026-01-15", "ticker": "PETR4", "kind": "Div", "gross": 20.0, "net": 20.0},
        {"pay_date": "2026-02-10", "ticker": "PETR4", "kind": "JSCP", "gross": 10.0, "net": 8.5},
    ]


def test_performance_returns_full_body(dbSession, monkeypatch):
    # Metric-subset moved client-side: server always returns the full body.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed_wallet(client)
    body = client.get("/wallet/performance?from=2026-01-01&to=2026-01-11").json()
    assert set(body) == {"twr", "twr_annualized", "volatility", "dividends_received", "price_return"}
    assert body["twr"] == pytest.approx(0.2)


def test_performance_window_is_explicit_dates_only(dbSession, monkeypatch):
    # Preset->date resolution moved client-side: explicit from/to still works.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_mock_get))
    client, _, _ = make_wallet_client(db=dbSession)
    _seed_wallet(client)
    explicit = client.get("/wallet/performance?from=2026-01-01&to=2026-01-11").json()
    assert explicit["twr"] == pytest.approx(0.2)


def _patch_closes(monkeypatch, series):
    def fake(cls, ticker):
        return list(series)

    monkeypatch.setattr("main.app.wallet.analytics.PositionsManager.fetchPadraoCloses", classmethod(fake))


def test_progression_invested_uses_cost_basis(monkeypatch):
    # Sell-all at a profit: invested drops to the sold cost basis (1000), not proceeds (2000).
    _patch_closes(monkeypatch, [(date(2026, 1, 2), 10.0), (date(2026, 1, 5), 20.0), (date(2026, 1, 6), 20.0)])
    entriesSnap = (
        ("PETR4", "2026-01-02", "Compra", "100", "10", "0", 1),
        ("PETR4", "2026-01-05", "Venda", "100", "20", "0", 2),
    )
    body = AnalyticsManager.cachedProgression(1, "2026-01-01", "2026-01-06", entriesSnap)
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-02"]["invested"] == 1000.0
    assert byDate["2026-01-05"]["invested"] == 0.0
    assert byDate["2026-01-06"]["invested"] == 0.0


def test_progression_invested_partial_sale_keeps_cost_basis(monkeypatch):
    _patch_closes(monkeypatch, [(date(2026, 1, 2), 10.0), (date(2026, 1, 5), 12.0)])
    entriesSnap = (
        ("PETR4", "2026-01-02", "Compra", "100", "10", "0", 1),
        ("PETR4", "2026-01-05", "Venda", "50", "12", "0", 2),
    )
    body = AnalyticsManager.cachedProgression(1, "2026-01-01", "2026-01-05", entriesSnap)
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-05"]["invested"] == 500.0


def test_progression_sell_without_position_does_not_divide_by_zero(monkeypatch):
    # Sell more than held (borrow): the basis math must not divide by zero.
    _patch_closes(monkeypatch, [(date(2026, 1, 5), 20.0)])
    entriesSnap = (("PETR4", "2026-01-05", "Venda", "10", "20", "0", 1),)
    body = AnalyticsManager.cachedProgression(1, "2026-01-01", "2026-01-05", entriesSnap)
    byDate = {point["date"]: point for point in body["points"]}
    assert byDate["2026-01-05"]["invested"] == 0.0


def test_cached_progression_accepts_no_recalc_key():
    body = AnalyticsManager.cachedProgression(1, "2026-01-01", "2026-01-02", ())
    assert body == {"granularity": "daily", "from": "2026-01-01", "to": "2026-01-02", "points": []}
