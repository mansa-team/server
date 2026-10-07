"""Batch live quotations: concurrency + per-ticker fallback (reviewer issue #13)."""

from unittest.mock import MagicMock

import pytest
import requests

from main.app.stocks_api import query as queryMod
from main.app.stocks_api.query import fetchLive as originalFetchLive
from main.app.stocks_api.query import queryLiveCotation, queryLiveCotations


def _envelope(ticker, price=10.0):
    return {
        "search": ticker,
        "type": "realtime-cotation",
        "timestamp": "2026-01-01T10:00:00",
        "count": 1,
        "data": [
            {
                "TICKER": ticker,
                "PRECO ATUAL": price,
                "PRECO ORIGINAL": price,
                "PRECO MINIMO": price,
                "PRECO MAXIMO": price,
                "PRECO MEDIO": price,
            }
        ],
    }


def _mock_b3_session(monkeypatch, payload):
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.json.return_value = payload
    mock_resp.raise_for_status = MagicMock()
    mock_session.get.return_value = mock_resp
    monkeypatch.setattr(queryMod, "getSession", lambda: mock_session)


def test_batch_returns_all_tickers(monkeypatch):
    monkeypatch.setattr(queryMod, "fetchLive", lambda s: _envelope(s, 10.0))
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 2
    assert out["errors"] == {}
    assert {row["TICKER"] for row in out["data"]} == {"PETR4", "VALE3"}


def test_batch_isolates_per_ticker_failure(monkeypatch):
    def fake(search):
        if search == "VALE3":
            raise requests.ConnectionError("down")
        return _envelope(search, 10.0)

    monkeypatch.setattr(queryMod, "fetchLive", fake)
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 1
    assert out["data"][0]["TICKER"] == "PETR4"
    assert out["errors"] == {"VALE3": "B3 realtime unavailable"}


def test_batch_flags_malformed_payload(monkeypatch):
    _mock_b3_session(monkeypatch, {"BizSts": {"cd": "OK"}})
    out = queryLiveCotations("PETR4")
    assert out["count"] == 0
    assert "PETR4" in out["errors"]


def test_single_distinguishes_network_from_malformed(monkeypatch):
    monkeypatch.setattr(
        queryMod,
        "fetchLive",
        lambda s: (_ for _ in ()).throw(requests.Timeout("t")),
    )
    with pytest.raises(Exception) as exc:
        queryLiveCotation("PETR4")
    assert exc.value.status_code == 503

    _mock_b3_session(monkeypatch, {"unexpected": 1})
    monkeypatch.setattr(queryMod, "fetchLive", originalFetchLive)
    with pytest.raises(Exception) as exc:
        queryLiveCotation("PETR4")
    assert exc.value.status_code == 502
