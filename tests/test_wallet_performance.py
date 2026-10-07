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


def _flat_series_with_one_div(url, params=None, headers=None, timeout=None):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            rows = [{"DATA": f"{d:02d}-01-2026", "PRECO": 10.0} for d in range(1, 10)]
            rows += [{"DATA": "10-01-2026", "PRECO": 10.0}, {"DATA": "11-01-2026", "PRECO": 11.0}]
            return {"data": rows}

    return Resp()


def test_performance_splits_price_and_dividends(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _flat_series_with_one_div)
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
    body = client.get("/wallet/performance?ticker=PETR4&from=2026-01-01&to=2026-01-11").json()
    assert body["twr"] == pytest.approx(0.21)
    assert body["price_return"] == pytest.approx(0.1)
    assert body["dividends_received"] == 10.0
    assert body["volatility"] > 0


def test_performance_defaults_to_lifetime_window(dbSession, monkeypatch):
    def wrapped_series(url, params=None, headers=None, timeout=None):
        class Resp:
            status_code = 200

            @staticmethod
            def json():
                rows = [{"DATA": f"{d:02d}-01-2026", "PRECO": 10.0} for d in range(1, 10)]
                rows += [{"DATA": "10-01-2026", "PRECO": 10.0}, {"DATA": "11-01-2026", "PRECO": 11.0}]
                return {"data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": rows}]}

        return Resp()

    monkeypatch.setattr(requests, "get", wrapped_series)
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
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
    body = client.get("/wallet/performance").json()
    assert body["twr"] == pytest.approx(0.1)
    assert body["price_return"] == pytest.approx(0.1)
    assert set(body) == {"twr", "twr_annualized", "volatility", "dividends_received", "price_return"}
