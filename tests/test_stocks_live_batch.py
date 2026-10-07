"""Batch live quotations: concurrency + per-ticker fallback (reviewer issue #13)."""

from unittest.mock import MagicMock

import pytest
import requests

from main.app.stocks_api import query as queryMod
from main.app.stocks_api.query import queryLiveCotations


def _payload(ticker, price=10.0):
    return {
        "BizSts": {"cd": "OK"},
        "Msg": {"dtTm": "2026-01-01T10:00:00"},
        "Trad": [
            {
                "scty": {
                    "symb": ticker,
                    "SctyQtn": {
                        "curPrc": price,
                        "opngPric": price,
                        "minPric": price,
                        "maxPric": price,
                        "avrgPric": price,
                    },
                }
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


def _mock_b3_multi(monkeypatch, byTicker):
    mock_session = MagicMock()

    def _get(url, timeout=5):
        symbol = url.rsplit("/", 1)[-1]
        mock_resp = MagicMock()
        mock_resp.json.return_value = byTicker[symbol]
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_session.get.side_effect = _get
    monkeypatch.setattr(queryMod, "getSession", lambda: mock_session)


def test_batch_returns_all_tickers(monkeypatch):
    _mock_b3_multi(monkeypatch, {"PETR4": _payload("PETR4"), "VALE3": _payload("VALE3")})
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 2
    assert out["errors"] == {}
    assert {row["TICKER"] for row in out["data"]} == {"PETR4", "VALE3"}


def test_batch_isolates_per_ticker_failure(monkeypatch):
    mock_session = MagicMock()

    def _get(url, timeout=5):
        if url.endswith("/VALE3"):
            raise requests.ConnectionError("down")
        mock_resp = MagicMock()
        mock_resp.json.return_value = _payload("PETR4")
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    mock_session.get.side_effect = _get
    monkeypatch.setattr(queryMod, "getSession", lambda: mock_session)
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 1
    assert out["data"][0]["TICKER"] == "PETR4"
    assert out["errors"] == {"VALE3": "B3 realtime unavailable"}


def test_batch_flags_malformed_payload(monkeypatch):
    _mock_b3_session(monkeypatch, {"BizSts": {"cd": "OK"}})
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 0
    assert set(out["errors"]) == {"PETR4", "VALE3"}


def test_single_distinguishes_network_from_malformed(monkeypatch):
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.Timeout("t")
    monkeypatch.setattr(queryMod, "getSession", lambda: mock_session)
    with pytest.raises(Exception) as exc:
        queryLiveCotations("PETR4")
    assert exc.value.status_code == 503

    _mock_b3_session(monkeypatch, {"unexpected": 1})
    with pytest.raises(Exception) as exc:
        queryLiveCotations("PETR4")
    assert exc.value.status_code == 502
