"""Tests for the optional `quarterly` param on /stocks/historical (query.py + route)."""

import sys
import os
from datetime import datetime
from unittest.mock import MagicMock

import pytest
import pandas as pd
from fastapi import HTTPException
from sqlalchemy.exc import ProgrammingError

from main.app.stocks_api import build as buildModule
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


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return list(self._rows)


class _Stream:
    def __init__(self, columns, rows, chunkSize=2):
        self._columns = columns
        self._rows = rows
        self._chunkSize = chunkSize
        self._offset = 0

    def keys(self):
        return list(self._columns)

    def fetchmany(self, size):
        out = self._rows[self._offset : self._offset + min(size, self._chunkSize)]
        self._offset += len(out)
        return out

    def close(self):
        pass


class _FakeConn:
    def __init__(self, columns, rows, quarterlyRows=(), quarterlyError=None):
        self._columns = columns
        self._rows = rows
        self._quarterlyRows = list(quarterlyRows)
        self._quarterlyError = quarterlyError

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execution_options(self, **kwargs):
        return self

    def exec_driver_sql(self, statement):
        if statement.startswith("SHOW COLUMNS"):
            return _Rows([(column, "double") for column in self._columns])
        if "HISTORICO TRIMESTRAL" in statement:
            if self._quarterlyError is not None:
                raise self._quarterlyError
            return _Rows(self._quarterlyRows)
        return _Stream(self._columns, self._rows)


def build_cached_frame(tmp_path, monkeypatch, quarterlyRows=(), quarterlyError=None):
    monkeypatch.setattr(buildModule, "CACHE_FEATHER_PATH", tmp_path / "stocks_cache.feather")
    monkeypatch.setattr(buildModule, "CACHE_NESTED_PATH", tmp_path / "stocks_nested.feather")
    columns = ["TICKER", "NOME", "TIME", "LUCRO LIQUIDO 2023", "HISTORICO TRIMESTRAL"]
    rows = [
        ("TEST0", "Empresa 0", datetime(2024, 1, 15), 100.0, None),
        ("TEST1", "Empresa 1", datetime(2024, 2, 15), 110.0, None),
        ("TEST2", "Empresa 2", datetime(2024, 3, 15), 120.0, '{"MARGEM BRUTA 1T 2024": 0.0}'),
    ]
    fakeEngine = MagicMock()
    fakeEngine.connect.return_value = _FakeConn(columns, rows, quarterlyRows, quarterlyError)
    buildModule.buildFeatherCache(engine=fakeEngine)
    return pd.read_feather(tmp_path / "stocks_cache.feather")


class TestQuarterlyCacheBuild:
    def test_pivot_uses_metric_space_quarter_names(self):
        conn = _FakeConn(
            [],
            [],
            quarterlyRows=[
                ("AAAA3", '{"MARGEM BRUTA 1T 2024": 12.5, "MARGEM BRUTA 2T 2024": 13.0}'),
                ("BBBB4", '{"MARGEM BRUTA 1T 2024": 7.0}'),
                ("CCCC5", "not json"),
                ("DDDD6", "{}"),
            ],
        )
        frame = buildModule.loadQuarterlyFrame(conn)
        assert frame is not None
        assert set(frame.columns) == {"TICKER", "MARGEM BRUTA 1T 2024", "MARGEM BRUTA 2T 2024"}
        indexed = frame.set_index("TICKER")
        assert set(indexed.index) == {"AAAA3", "BBBB4"}
        assert indexed.loc["AAAA3", "MARGEM BRUTA 1T 2024"] == pytest.approx(12.5)
        assert pd.isna(indexed.loc["BBBB4", "MARGEM BRUTA 2T 2024"])

    def test_query_failure_returns_none(self):
        error = ProgrammingError("SELECT", {}, Exception("Unknown column 'HISTORICO TRIMESTRAL'"))
        assert buildModule.loadQuarterlyFrame(_FakeConn([], [], quarterlyError=error)) is None

    def test_cache_merges_quarterly_columns_across_chunks(self, tmp_path, monkeypatch):
        frame = build_cached_frame(tmp_path, monkeypatch, quarterlyRows=[("TEST2", '{"MARGEM BRUTA 1T 2024": 42.5}')])
        assert "MARGEM BRUTA 1T 2024" in frame.columns
        assert "HISTORICO TRIMESTRAL" not in frame.columns
        indexed = frame.set_index("TICKER")
        assert indexed.loc["TEST2", "MARGEM BRUTA 1T 2024"] == pytest.approx(42.5)
        assert pd.isna(indexed.loc["TEST0", "MARGEM BRUTA 1T 2024"])

        result = queryModule.queryHistorical(
            cacheManager=make_manager(frame), search="TEST2", fields="MARGEM BRUTA", quarterly="T1"
        )
        assert result["data"][0]["MARGEM BRUTA 1T 2024"] == pytest.approx(42.5)

    def test_cache_builds_when_quarterly_query_fails(self, tmp_path, monkeypatch):
        error = ProgrammingError("SELECT", {}, Exception("Unknown column 'HISTORICO TRIMESTRAL'"))
        frame = build_cached_frame(tmp_path, monkeypatch, quarterlyError=error)
        assert "LUCRO LIQUIDO 2023" in frame.columns
        assert "HISTORICO TRIMESTRAL" not in frame.columns
        assert not any("1T 2024" in column for column in frame.columns)

    def test_categorize_columns_real_quarter_name(self):
        historical, fundamental = queryModule.categorizeColumns(["MARGEM BRUTA 1T 2024", "MARGEM BRUTA 2024"])
        assert historical["MARGEM BRUTA 1T"] == [2024]
        assert historical["MARGEM BRUTA"] == [2024]
        assert fundamental == []
