"""Tests for the optional `quarterly` param on /stocks/historical (query.py + route)."""

import sys
import os
from unittest.mock import MagicMock

import pytest
import pandas as pd
from fastapi import HTTPException

from main.app.stocks_api import query as queryModule
from main.app.stocks_api.cache import StocksCacheManager, stocksCache
from cashews import cache as cashews_cache

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    await cashews_cache.clear()
    yield
    await cashews_cache.clear()


def make_year_df(rows=2):
    data = {
        "TICKER": [f"TEST{i}" for i in range(rows)],
        "NOME": [f"Empresa {i}" for i in range(rows)],
        "TIME": pd.to_datetime([f"2024-0{i + 1}-15" for i in range(rows)]),
        "LUCRO LIQUIDO 2023": [100 + i * 10 for i in range(rows)],
        "LUCRO LIQUIDO 2022": [90 + i * 10 for i in range(rows)],
    }
    return pd.DataFrame(data)


def make_quarterly_df(rows=2):
    data = {
        "TICKER": [f"TEST{i}" for i in range(rows)],
        "NOME": [f"Empresa {i}" for i in range(rows)],
        "TIME": pd.to_datetime([f"2024-0{i + 1}-15" for i in range(rows)]),
        "LUCRO LIQUIDO 1T 2024": [10 + i for i in range(rows)],
        "LUCRO LIQUIDO 2T 2024": [20 + i for i in range(rows)],
        "LUCRO LIQUIDO 3T 2024": [30 + i for i in range(rows)],
        "LUCRO LIQUIDO 4T 2024": [40 + i for i in range(rows)],
    }
    return pd.DataFrame(data)


def make_manager(cache_df):
    mock_cache = MagicMock(spec=StocksCacheManager)
    mock_cache.STOCKS_CACHE = cache_df
    mock_cache.tickerIndex = {}
    return mock_cache


class TestQuarterlyQuery:
    def test_absent_quarterly_keeps_year_behavior(self):
        mgr = make_manager(make_year_df())
        result = queryModule.queryHistorical(cacheManager=mgr, search="TEST0", fields="LUCRO LIQUIDO")
        row = result["data"][0]
        assert "LUCRO LIQUIDO 2023" in row
        assert "LUCRO LIQUIDO 1T 2023" not in row

    def test_quarterly_T1_returns_quarter_columns(self):
        mgr = make_manager(make_quarterly_df())
        result = queryModule.queryHistorical(cacheManager=mgr, search="TEST0", fields="LUCRO LIQUIDO", quarterly="T1")
        row = result["data"][0]
        assert "LUCRO LIQUIDO 1T 2024" in row
        # single-quarter selection: other quarters are not returned
        assert "LUCRO LIQUIDO 2T 2024" not in row

    def test_quarterly_1T_normalized_like_T1(self):
        mgr = make_manager(make_quarterly_df())
        result = queryModule.queryHistorical(cacheManager=mgr, search="TEST0", fields="LUCRO LIQUIDO", quarterly="1T")
        assert "LUCRO LIQUIDO 1T 2024" in result["data"][0]

    @pytest.mark.parametrize("token", ["T0", "T5", "5T", "Q1", "bogus", "T1,2T"])
    def test_invalid_token_returns_400(self, token):
        mgr = make_manager(make_quarterly_df())
        with pytest.raises(HTTPException) as exc_info:
            queryModule.queryHistorical(cacheManager=mgr, search="TEST0", quarterly=token)
        assert exc_info.value.status_code == 400

    def test_trimester_carrying_field_returns_400(self):
        mgr = make_manager(make_quarterly_df())
        with pytest.raises(HTTPException) as exc_info:
            queryModule.queryHistorical(cacheManager=mgr, search="TEST0", fields="LUCRO LIQUIDO 1T", quarterly="T1")
        assert exc_info.value.status_code == 400

    def test_no_quarter_columns_returns_400(self):
        mgr = make_manager(make_year_df())
        with pytest.raises(HTTPException) as exc_info:
            queryModule.queryHistorical(cacheManager=mgr, search="TEST0", fields="LUCRO LIQUIDO", quarterly="T1")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "No quarterly data available in cache"


class TestQuarterlyRoute:
    def test_route_absent_quarterly_year_columns(self, stocks_http_client):
        with (
            patch_stocks_cache(make_year_df()),
        ):
            resp = stocks_http_client.get("/stocks/historical", params={"search": "TEST0", "fields": "LUCRO LIQUIDO"})
            assert resp.status_code == 200
            assert "LUCRO LIQUIDO 2023" in resp.json()["data"][0]

    def test_route_quarterly_columns(self, stocks_http_client):
        with patch_stocks_cache(make_quarterly_df()):
            resp = stocks_http_client.get(
                "/stocks/historical",
                params={"search": "TEST0", "fields": "LUCRO LIQUIDO", "quarterly": "T1"},
            )
            assert resp.status_code == 200
            assert "LUCRO LIQUIDO 1T 2024" in resp.json()["data"][0]

    def test_route_invalid_token_400(self, stocks_http_client):
        with patch_stocks_cache(make_quarterly_df()):
            resp = stocks_http_client.get("/stocks/historical", params={"search": "TEST0", "quarterly": "T9"})
            assert resp.status_code == 400

    def test_route_no_quarter_columns_400(self, stocks_http_client):
        with patch_stocks_cache(make_year_df()):
            resp = stocks_http_client.get(
                "/stocks/historical",
                params={"search": "TEST0", "fields": "LUCRO LIQUIDO", "quarterly": "T1"},
            )
            assert resp.status_code == 400
            assert resp.json()["error"] == "No quarterly data available in cache"


class _PatchStocksCache:
    def __init__(self, cache_df):
        self.cache_df = cache_df

    def __enter__(self):
        self.original_cache = stocksCache.STOCKS_CACHE
        self.original_index = stocksCache.tickerIndex
        stocksCache.STOCKS_CACHE = self.cache_df
        stocksCache.tickerIndex = {}
        return self

    def __exit__(self, *exc):
        stocksCache.STOCKS_CACHE = self.original_cache
        stocksCache.tickerIndex = self.original_index
        return False


def patch_stocks_cache(cache_df):
    return _PatchStocksCache(cache_df)
