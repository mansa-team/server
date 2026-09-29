"""Regression: historicalDividends() backfills VALOR ORIGINAL when "ov" is absent.

SI ships "ov" whenever a factor exists (adj=True rows); when absent, a NaN
placeholder keeps the column present (downstream tolerates NaN).
"""

import sys
from unittest.mock import MagicMock

import pandas as pd

# Stub research-repo `xango` module (main/app/scraper_b3/scraper.py:20
# `from xango import calculateInvestingScore` — absent here).
if "xango" not in sys.modules:
    _xango_stub = MagicMock()
    _xango_stub.calculateInvestingScore = MagicMock(return_value={})
    sys.modules["xango"] = _xango_stub

from main.app.scraper_b3.scraper import B3Scraper


def _payload(records):
    return {"assetEarningsYearlyModels": [], "assetEarningsModels": records}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _scraper(payload):
    # Bypass __init__ (hits network: cloudscraper + SELIC fetch).
    s = B3Scraper.__new__(B3Scraper)
    s.requests = MagicMock()
    s.requests.get.return_value = _FakeResp(payload)
    return s


def _rec(ed="21/08/2026", pd="21/12/2026", v=1.0, adj=0.5):
    return {
        "y": 0,
        "m": 0,
        "d": 0,
        "ed": ed,
        "pd": pd,
        "et": "JCP",
        "etd": "Juros Sobre Capital Proprio",
        "v": v,
        "sv": str(v),
        "sov": "-",
        "adj": adj,
    }


class TestHistoricalDividendsOvDrift:
    def test_missing_ov_yields_nan(self):
        df = _scraper(_payload([_rec(v=0.20250435, adj=False)])).historicalDividends("PETR4")
        recs = df["HISTORICO DIVIDENDOS"].iloc[0]
        assert pd.isna(recs[0]["VALOR ORIGINAL"])

    def test_ov_present_is_kept(self):
        rec = {**_rec(v=0.01765, adj=True), "ov": 0.015}
        df = _scraper(_payload([rec])).historicalDividends("PETR4")
        recs = df["HISTORICO DIVIDENDOS"].iloc[0]
        assert recs[0]["VALOR ORIGINAL"] == 0.015
