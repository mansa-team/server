import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest
import pytest_asyncio
from cashews import cache as cashewsCache
from fastapi import Response

from main.app.stocks_api import cache as cache_mod
from main.app.stocks_api.cache import STALE_AFTER_SECONDS
from main.controller import stocksapi_controller as mod


def _seconds(ttl: str) -> int:
    match = re.fullmatch(r"(\d+)([smhd])", ttl)
    assert match, f"unparseable ttl: {ttl}"
    value, unit = match.groups()
    return int(value) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def test_long_endpoints_share_one_six_hour_constant():
    assert mod.STOCKS_TTL == "6h"
    assert _seconds(mod.STOCKS_TTL) == 6 * 3600


def test_cache_control_max_age_matches_the_decorator_ttl():
    assert mod.STOCKS_MAX_AGE == _seconds(mod.STOCKS_TTL)
    assert mod.LIVE_MAX_AGE == _seconds(mod.LIVE_TTL)


def test_endpoint_ttl_never_exceeds_the_staleness_policy():
    assert _seconds(mod.STOCKS_TTL) <= STALE_AFTER_SECONDS


def test_live_ttl_is_not_widened():
    assert mod.LIVE_TTL == "15s"


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def setup_cache():
    cashewsCache.setup("mem://")
    yield
    await cashewsCache.clear()


def _flush():
    asyncio.run(cashewsCache.clear())


def test_fields_second_call_is_a_cache_hit(monkeypatch):
    _flush()
    calls = []

    def fakeCategorize(cols):
        calls.append(tuple(cols))
        return {"A": [2024]}, ["P/L"]

    monkeypatch.setattr(mod, "categorizeColumns", fakeCategorize)
    monkeypatch.setattr(mod, "generateAbbreviations", lambda historical, fundamental: {"A": "A"})
    monkeypatch.setattr(mod, "getNest", lambda *a: {})
    monkeypatch.setattr(
        mod, "stocksCache", SimpleNamespace(STOCKS_CACHE=pd.DataFrame({"TICKER": ["PETR4"]}), nestedSample=None)
    )

    response = Response()
    first = mod.listFields(response)
    second = mod.listFields(Response())

    assert first == second
    assert calls == [("TICKER",)]  # computed once; the second call is a cache hit
    assert response.headers["Cache-Control"] == f"public, max-age={mod.STOCKS_MAX_AGE}"


def test_fields_503_is_not_cached(monkeypatch):
    _flush()
    monkeypatch.setattr(mod, "stocksCache", SimpleNamespace(STOCKS_CACHE=None))

    for _ in range(2):
        with pytest.raises(mod.HTTPException) as exc:
            mod.listFields(Response())
        assert exc.value.status_code == 503


def test_feather_reload_drops_cached_bodies(monkeypatch):
    _flush()
    asyncio.run(cashewsCache.set("stocks:fields", {"probe": True}, expire=3600))
    assert asyncio.run(cashewsCache.get("stocks:fields", default=None)) == {"probe": True}

    # keep the reload cheap: no real feather file, no abbreviation rebuild
    monkeypatch.setattr(cache_mod, "readFeatherDataFrame", lambda path: (pd.DataFrame({"TICKER": ["PETR4"]}), True))
    monkeypatch.setattr(cache_mod, "CACHE_NESTED_PATH", Path("missing.feather"))
    monkeypatch.setattr("main.app.stocks_api.compress.rebuildAbbrevs", lambda: None)

    manager = cache_mod.stocksCache
    saved = (manager.STOCKS_CACHE, manager.tickerIndex, manager.nestedSample, manager.lastCacheUpdate)
    try:
        manager.loadFromFeather()
    finally:
        manager.STOCKS_CACHE, manager.tickerIndex, manager.nestedSample, manager.lastCacheUpdate = saved

    assert asyncio.run(cashewsCache.get("stocks:fields", default=None)) is None
