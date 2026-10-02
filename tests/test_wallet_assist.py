from datetime import date as dateType
from unittest.mock import MagicMock

import pytest
import requests
from cashews import cache as cashewsCache

import main.models.wallet  # noqa: F401
from main.app.wallet.market_data import MarketDataManager
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _fundamental_dup(url, params=None, headers=None, timeout=None):
    assert timeout == 3

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": [
                    {"TICKER": "PETR4", "NOME": "PETROBRAS PN"},
                    {"TICKER": "VALE3", "NOME": "VALE ON"},
                    {"TICKER": "PETR4", "NOME": "PETROBRAS PN"},
                ],
            }

    return Resp()


def test_tickers_shape_and_dedup(dbSession, monkeypatch):
    calls: list = []

    def counting(url, params=None, headers=None, timeout=None):
        calls.append(params)
        return _fundamental_dup(url, params, headers, timeout)

    monkeypatch.setattr(requests, "get", counting)
    client, _, _ = make_wallet_client(db=dbSession)
    first = client.get("/wallet/tickers")
    assert first.status_code == 200
    assert first.json() == [
        {"ticker": "PETR4", "nome": "PETROBRAS PN"},
        {"ticker": "VALE3", "nome": "VALE ON"},
    ]
    second = client.get("/wallet/tickers")
    assert second.status_code == 200
    assert len(calls) == 1


def test_tickers_upstream_fail_returns_empty(dbSession, monkeypatch):
    def boom(url, params=None, headers=None, timeout=None):
        raise requests.Timeout()

    monkeypatch.setattr(requests, "get", boom)
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.get("/wallet/tickers")
    assert resp.status_code == 200
    assert resp.json() == []


def _closes(monkeypatch, rows):
    manager = MagicMock()
    manager.fetchPadraoCloses.return_value = rows
    monkeypatch.setattr(MarketDataManager, "fetchPadraoCloses", manager.fetchPadraoCloses)


def test_close_exact_date(dbSession, monkeypatch):
    _closes(
        monkeypatch,
        [(dateType(2026, 9, 25), 28.5), (dateType(2026, 9, 28), 29.0)],
    )
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.get("/wallet/close", params={"ticker": "PETR4", "date": "2026-09-25"})
    assert resp.status_code == 200
    assert resp.json() == {"ticker": "PETR4", "date": "2026-09-25", "close": 28.5}


def test_close_weekend_falls_back_to_friday(dbSession, monkeypatch):
    _closes(
        monkeypatch,
        [(dateType(2026, 9, 25), 28.5), (dateType(2026, 9, 28), 29.0)],
    )
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.get("/wallet/close", params={"ticker": "PETR4", "date": "2026-09-26"})
    assert resp.status_code == 200
    assert resp.json() == {"ticker": "PETR4", "date": "2026-09-26", "close": 28.5}


def test_close_unknown_ticker_404(dbSession, monkeypatch):
    _closes(monkeypatch, [])
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.get("/wallet/close", params={"ticker": "XXXX4", "date": "2026-09-25"})
    assert resp.status_code == 404


def test_close_bad_date_422(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.get("/wallet/close", params={"ticker": "PETR4", "date": "not-a-date"})
    assert resp.status_code == 422
