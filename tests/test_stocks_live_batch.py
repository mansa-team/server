"""Batch live quotations: concurrency + per-ticker fallback (reviewer issue #13)."""

import pytest
import requests

from main.app.stocks_api import query as queryMod
from main.app.stocks_api.query import queryLiveCotation, queryLiveCotations


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


def test_batch_returns_all_tickers(monkeypatch):
    monkeypatch.setattr(queryMod, "fetchLivePayload", lambda s: _payload(s, 10.0))
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 2
    assert out["errors"] == {}
    assert {row["TICKER"] for row in out["data"]} == {"PETR4", "VALE3"}


def test_batch_isolates_per_ticker_failure(monkeypatch):
    def fake(search):
        if search == "VALE3":
            raise requests.ConnectionError("down")
        return _payload(search, 10.0)

    monkeypatch.setattr(queryMod, "fetchLivePayload", fake)
    out = queryLiveCotations("PETR4,VALE3")
    assert out["count"] == 1
    assert out["data"][0]["TICKER"] == "PETR4"
    assert out["errors"] == {"VALE3": "B3 realtime unavailable"}


def test_batch_flags_malformed_payload(monkeypatch):
    monkeypatch.setattr(queryMod, "fetchLivePayload", lambda s: {"BizSts": {"cd": "OK"}})
    out = queryLiveCotations("PETR4")
    assert out["count"] == 0
    assert "PETR4" in out["errors"]


def test_single_distinguishes_network_from_malformed(monkeypatch):
    monkeypatch.setattr(
        queryMod,
        "fetchLivePayload",
        lambda s: (_ for _ in ()).throw(requests.Timeout("t")),
    )
    with pytest.raises(Exception) as exc:
        queryLiveCotation("PETR4")
    assert exc.value.status_code == 503

    monkeypatch.setattr(queryMod, "fetchLivePayload", lambda s: {"unexpected": 1})
    with pytest.raises(Exception) as exc:
        queryLiveCotation("PETR4")
    assert exc.value.status_code == 502
