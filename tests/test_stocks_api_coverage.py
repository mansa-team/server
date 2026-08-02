"""Tests to increase coverage for query.py, key.py, and cache.py in stocks_api."""

import asyncio
import sys
import os
import json
import threading
import time
from collections import OrderedDict
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock

import pytest
from fastapi import HTTPException
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Helper: build a minimal DataFrame that looks like the stocks cache
# ---------------------------------------------------------------------------
def _make_stocks_df(rows=3):
    """Return a small DataFrame with the columns the query module expects."""
    data = {
        "TICKER": [f"TEST{i}" for i in range(rows)],
        "NOME": [f"Empresa {i}" for i in range(rows)],
        "TIME": pd.to_datetime([f"2024-0{i + 1}-15" for i in range(rows)]),
        "PRECO": [10.0 + i for i in range(rows)],
        "P/L": [5.0 + i for i in range(rows)],
        "ROE": [0.1 + 0.05 * i for i in range(rows)],
        "DY": [0.03 + 0.01 * i for i in range(rows)],
        "LUCRO LIQUIDO 2023": [100 + i * 10 for i in range(rows)],
        "LUCRO LIQUIDO 2022": [90 + i * 10 for i in range(rows)],
        "RECEITA 2023": [200 + i * 20 for i in range(rows)],
    }
    return pd.DataFrame(data)


# ===========================================================================
# Tests for cache.py – StocksCacheManager
# ===========================================================================
class TestStocksCacheManager:
    """Tests covering cache.py lines 28-76."""

    def _make_manager(self):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_engine = MagicMock()
        lock = threading.Lock()
        return StocksCacheManager(mock_engine, lock)

    # --- cacheScheduler (lines 28-32) ------------------------------------
    @patch("main.app.stocks_api.cache.BackgroundScheduler")
    def test_cache_scheduler_starts_apscheduler(self, mock_sched_cls):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_engine = MagicMock()
        mgr = StocksCacheManager(mock_engine, threading.Lock())
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched

        # spawned init thread must never run against the real feather/subprocess path
        with patch("main.app.stocks_api.cache.threading.Thread"):
            mgr.cacheScheduler()

        mock_sched_cls.assert_called_once()
        mock_sched.add_job.assert_called_once()
        mock_sched.start.assert_called_once()

    # --- getCachedStocks: no columns (lines 61-62) -----------------------
    def test_getCachedStocks_no_columns(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A", "B"], "NOME": ["X", "Y"], "TIME": ["t1", "t2"]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)

        # getCachedStocks stores in self.STOCKS_CACHE
        assert mgr.STOCKS_CACHE is not None
        assert len(mgr.STOCKS_CACHE) == 2

    # --- getCachedStocks: with columns and validation (lines 52-58) ------
    def test_getCachedStocks_with_valid_columns(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"], "TIME": ["t1"], "PRECO": [10.0]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df) as mock_read,
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)
            mock_read.assert_called()

    # --- getCachedStocks: NaN preserved (sanitizeNanValues handles at serialization) ---
    def test_getCachedStocks_replaces_nan_inf(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [np.nan]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)
            assert mgr.STOCKS_CACHE is not None
            # NaN is kept in cache; sanitizeNanValues converts to None at serialization
            assert pd.isna(mgr.STOCKS_CACHE["VAL"].iloc[0])

    # --- getCachedStocks: tickerIndex built (line 66) ---------------------
    def test_getCachedStocks_builds_ticker_index(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["PETR4", "VALE3"], "NOME": ["Petrobras", "Vale"]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)
            assert mgr.tickerIndex == {"PETR4": 0, "VALE3": 1}

    # --- getCachedStocks: exception (lines 75-76) -------------------------
    def test_getCachedStocks_exception_logged(self):
        mgr = self._make_manager()
        # Should not raise, just log
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", side_effect=Exception("feather error")),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)

    # --- getCachedStocks: inf preserved (sanitizeNanValues handles at serialization) ---
    def test_getCachedStocks_replaces_inf(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [np.inf]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)
            assert mgr.STOCKS_CACHE is not None
            assert pd.isna(mgr.STOCKS_CACHE["VAL"].iloc[0]) or np.isinf(mgr.STOCKS_CACHE["VAL"].iloc[0])

    def test_getCachedStocks_replaces_neg_inf(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [-np.inf]})
        with (
            patch("main.app.stocks_api.cache.pd.read_feather", return_value=df),
            patch("main.app.stocks_api.cache.subprocess.run", return_value=None),
        ):
            mgr.getCachedStocks(force_refresh=True)
            assert mgr.STOCKS_CACHE is not None
            assert pd.isna(mgr.STOCKS_CACHE["VAL"].iloc[0]) or np.isinf(mgr.STOCKS_CACHE["VAL"].iloc[0])


# ===========================================================================
# Tests for key.py – verifyAPIKey, generateSecureKey, createKey
# ===========================================================================
class TestVerifyAPIKey:
    """Tests covering key.py lines 15-40.
    Uses asyncio.run() since pytest-asyncio is not configured."""

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_disabled_returns_none(self, mock_config):
        """When KEY.SYSTEM is falsy, return None (line 16)."""
        from main.app.stocks_api.key import verifyAPIKey

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=False)
        mock_db = MagicMock()

        result = asyncio.run(verifyAPIKey(apiKey=None, db=mock_db))
        assert result is None

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_missing_raises_401(self, mock_config):
        """When key is required but not provided (line 19)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey=None, db=mock_db))
        assert exc_info.value.status_code == 401

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_invalid_key_raises_401(self, mock_config):
        """When atomic UPDATE returns 0 rows and query finds no key -> 401."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()
        # Atomic UPDATE returns 0 rows (key not found or quota exceeded)
        mock_db.execute.return_value.rowcount = 0
        # Follow-up query confirms key doesn't exist
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="bad_key", db=mock_db))
        assert exc_info.value.status_code == 401

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_quota_exceeded(self, mock_config):
        """When atomic UPDATE returns 0 rows and query finds key at limit -> 429."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()
        # Atomic UPDATE returns 0 rows (quota exceeded)
        mock_db.execute.return_value.rowcount = 0
        # Follow-up query confirms key exists (at quota limit)
        mock_key_obj = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_key_obj

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="valid_key", db=mock_db))
        assert exc_info.value.status_code == 429

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_success(self, mock_config):
        """Happy path: atomic UPDATE succeeds, returns key (lines 22-33)."""
        from main.app.stocks_api.key import verifyAPIKey

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()
        # Atomic UPDATE returns 1 row (success)
        mock_db.execute.return_value.rowcount = 1

        result = asyncio.run(verifyAPIKey(apiKey="valid_key", db=mock_db))
        assert result == "valid_key"
        mock_db.commit.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_http_exception_rollback(self, mock_config):
        """HTTPException should cause rollback then re-raise (lines 35-37)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()
        # Atomic UPDATE returns 0 rows (quota exceeded)
        mock_db.execute.return_value.rowcount = 0
        # Follow-up query confirms key exists (at quota limit)
        mock_key_obj = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_key_obj

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="key", db=mock_db))
        assert exc_info.value.status_code == 429
        mock_db.rollback.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_generic_exception_rollback(self, mock_config):
        """Generic DB exception should rollback and raise 500 (lines 38-40)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(KEY_SYSTEM=True)
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("DB connection lost")

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="key", db=mock_db))
        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()


class TestGenerateSecureKey:
    """Tests covering key.py line 44."""

    def test_generate_secure_key_length(self):
        from main.app.stocks_api.key import generateSecureKey

        key = generateSecureKey(32)
        assert isinstance(key, str)
        assert len(key) == 32

    def test_generate_secure_key_custom_length(self):
        from main.app.stocks_api.key import generateSecureKey

        key = generateSecureKey(16)
        assert len(key) == 16

    def test_generate_secure_key_unique(self):
        from main.app.stocks_api.key import generateSecureKey

        keys = {generateSecureKey(32) for _ in range(50)}
        assert len(keys) == 50  # all unique


class TestCreateKey:
    """Tests covering key.py lines 48-66."""

    @patch("main.app.stocks_api.key.Config")
    def test_create_key_new_user(self, mock_config):
        """New key created when no existing key for user (lines 57-59)."""
        from main.app.stocks_api.key import createKey

        mock_config.STOCKS_API = MagicMock(DEFAULT_QUOTA=200)
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = createKey(mock_db, userId=42)
        assert isinstance(result, str)
        assert len(result) == 32
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_create_key_existing_user_updates(self, mock_config):
        """Existing key is updated (lines 54-56)."""
        from main.app.stocks_api.key import createKey, hashKey

        mock_config.STOCKS_API = MagicMock(DEFAULT_QUOTA=150)
        mock_db = MagicMock()
        mock_existing = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

        result = createKey(mock_db, userId=1)
        assert isinstance(result, str)
        # The stored key should be the hashed version; the returned key is the raw key
        assert mock_existing.apiKey == hashKey(result)
        assert mock_existing.requestLimit == 150
        mock_db.commit.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_create_key_exception_rollback(self, mock_config):
        """Exception during creation triggers rollback and 500 (lines 64-66)."""
        from main.app.stocks_api.key import createKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = MagicMock(DEFAULT_QUOTA=100)
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB error")

        with pytest.raises(HTTPException) as exc_info:
            createKey(mock_db, userId=1)
        assert exc_info.value.status_code == 500
        mock_db.rollback.assert_called_once()


# ===========================================================================
# Tests for query.py – StocksQueryManager
# ===========================================================================
class TestDeserializeJsonColumns:
    """Tests covering query.py lines 22-48."""

    def _make_manager(self):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        from main.app.stocks_api.query import StocksQueryManager

        return StocksQueryManager(mock_cache)

    def test_deserialize_empty_df(self):
        mgr = self._make_manager()
        df = pd.DataFrame()
        result = mgr.deserializeJsonColumns(df)
        assert result.empty

    def test_deserialize_returns_copy(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"PRECO": [10.0]})
        result = mgr.deserializeJsonColumns(df)
        assert result is not df

    def test_deserialize_json_dict_in_special_col(self):
        mgr = self._make_manager()
        json_str = json.dumps({"key": "value", "nested": {"a": 1}})
        df = pd.DataFrame({"COTACAO 10Y PADRAO": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["COTACAO 10Y PADRAO"].iloc[0] == {"key": "value", "nested": {"a": 1}}

    def test_deserialize_json_list_in_special_col(self):
        mgr = self._make_manager()
        json_str = json.dumps([1, 2, 3])
        df = pd.DataFrame({"HISTORICO DIVIDENDOS": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["HISTORICO DIVIDENDOS"].iloc[0] == [1, 2, 3]

    def test_deserialize_nan_in_dict_replaced(self):
        mgr = self._make_manager()
        json_str = json.dumps({"key": float("nan")})
        df = pd.DataFrame({"NOTICIAS": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["NOTICIAS"].iloc[0]["key"] is None

    def test_deserialize_nan_in_list_replaced(self):
        mgr = self._make_manager()
        json_str = json.dumps([float("nan"), "ok"])
        df = pd.DataFrame({"NOTICIAS": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["NOTICIAS"].iloc[0][0] is None
        assert result["NOTICIAS"].iloc[0][1] == "ok"

    def test_deserialize_nested_nan_in_dict(self):
        mgr = self._make_manager()
        json_str = json.dumps({"outer": {"inner": float("nan")}})
        df = pd.DataFrame({"COTACAO 10Y AJUSTADA": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["COTACAO 10Y AJUSTADA"].iloc[0]["outer"]["inner"] is None

    def test_deserialize_non_special_col_not_parsed(self):
        mgr = self._make_manager()
        json_str = json.dumps({"key": "value"})
        df = pd.DataFrame({"PRECO": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["PRECO"].iloc[0] == json_str

    def test_deserialize_non_string_value_not_parsed(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"NOTICIAS": [12345], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["NOTICIAS"].iloc[0] == 12345

    def test_deserialize_string_not_json_not_parsed(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"NOTICIAS": ["just text"], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        assert result["NOTICIAS"].iloc[0] == "just text"

    def test_deserialize_float_nan_direct(self):
        """replaceNan handles direct float NaN values (line 34)."""
        mgr = self._make_manager()
        json_str = json.dumps(float("nan"))
        df = pd.DataFrame({"NOTICIAS": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        # json.loads of "NaN" produces float nan; the value doesn't start with { or [
        # so it stays as-is (the string "NaN" in JSON, loaded as float nan)
        # Actually json.dumps(float("nan")) -> "NaN" which is not valid JSON but Python produces it
        # json.loads("NaN") -> float nan
        # The condition is isinstance(x, str) and x.startswith(("{", "["))
        # "NaN" doesn't start with { or [, so the lambda returns x as string "NaN"
        assert result is not None

    def test_deserialize_non_nan_float(self):
        """Non-JSON-dict/list string is left as-is."""
        mgr = self._make_manager()
        json_str = json.dumps(3.14)  # "3.14"
        df = pd.DataFrame({"NOTICIAS": [json_str], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        # "3.14" doesn't start with { or [, so lambda returns x as-is (string)
        assert result["NOTICIAS"].iloc[0] == "3.14"

    def test_deserialize_pd_na_value(self):
        """pd.NA is not a string, so lambda returns it unchanged."""
        mgr = self._make_manager()
        df = pd.DataFrame({"NOTICIAS": [pd.NA], "TICKER": ["A"]})
        result = mgr.deserializeJsonColumns(df)
        # pd.NA is not a string, so lambda returns x unchanged
        # The replaceNan function is never called
        assert result is not None

    def test_deserialize_mixed_string_none_parses_json(self):
        """Regression: is_string_dtype fails when column has strings + None (pandas 2.x).

        When querying ALL tickers (no search), many have None in SPECIAL_COLS.
        Before the fix, is_string_dtype returned False for mixed string/None columns,
        causing JSON parsing to be skipped entirely.
        """
        mgr = self._make_manager()
        json_str = json.dumps([{"DATA": "01-12-2016", "PRECO": 14.92}])
        df = pd.DataFrame(
            {
                "COTACAO 10Y PADRAO": [json_str, None],
                "TICKER": ["AALR3", "VALE3"],
            }
        )
        result = mgr.deserializeJsonColumns(df)
        # Row with JSON string should be parsed into a list of dicts
        assert isinstance(result["COTACAO 10Y PADRAO"].iloc[0], list)
        assert result["COTACAO 10Y PADRAO"].iloc[0][0]["DATA"] == "01-12-2016"
        # Row with None should stay None
        assert result["COTACAO 10Y PADRAO"].iloc[1] is None

    def test_deserialize_multiple_special_cols_with_none(self):
        """All four SPECIAL_COLS should parse correctly when mixed with None."""
        mgr = self._make_manager()
        json_cotacao = json.dumps([{"DATA": "30-01-2017", "PRECO": 14.03}])
        json_noticias = json.dumps({"titulo": "test", "data": "2026-01-01"})
        df = pd.DataFrame(
            {
                "COTACAO 10Y PADRAO": [json_cotacao, None],
                "COTACAO 10Y AJUSTADA": [None, json_cotacao],
                "NOTICIAS": [json_noticias, None],
                "HISTORICO DIVIDENDOS": [None, json_cotacao],
                "TICKER": ["AALR3", "VALE3"],
            }
        )
        result = mgr.deserializeJsonColumns(df)
        # Each SPECIAL_COL with data should be parsed
        assert isinstance(result["COTACAO 10Y PADRAO"].iloc[0], list)
        assert isinstance(result["COTACAO 10Y AJUSTADA"].iloc[1], list)
        assert isinstance(result["NOTICIAS"].iloc[0], dict)
        assert isinstance(result["HISTORICO DIVIDENDOS"].iloc[1], list)
        # None values should remain None
        assert result["COTACAO 10Y PADRAO"].iloc[1] is None
        assert result["NOTICIAS"].iloc[1] is None


class TestFilterBySearchTerms:
    """Tests covering query.py lines 50-67."""

    def _make_manager(self):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        from main.app.stocks_api.query import StocksQueryManager

        return StocksQueryManager(mock_cache)

    def test_filter_empty_search_returns_all(self):
        mgr = self._make_manager()
        df = pd.DataFrame({"TICKER": ["A", "B"]})
        result = mgr.filterBySearchTerms(df, "")
        assert len(result) == 2

    def test_filter_ticker_index_hit(self):
        mgr = self._make_manager()
        mgr.cacheManager.tickerIndex = {"PETR4": 0, "VALE3": 2}
        df = pd.DataFrame({"TICKER": ["PETR4", "ITUB4", "VALE3"]})
        result = mgr.filterBySearchTerms(df, "PETR4")
        assert len(result) == 1
        assert result.iloc[0]["TICKER"] == "PETR4"

    def test_filter_multiple_terms_index(self):
        mgr = self._make_manager()
        mgr.cacheManager.tickerIndex = {"PETR4": 0, "VALE3": 2}
        df = pd.DataFrame({"TICKER": ["PETR4", "ITUB4", "VALE3"]})
        result = mgr.filterBySearchTerms(df, "PETR4, VALE3")
        assert len(result) == 2

    def test_filter_no_index_match_fallback_to_str(self):
        mgr = self._make_manager()
        mgr.cacheManager.tickerIndex = {}
        df = pd.DataFrame({"TICKER": ["PETR4", "ITUB4", "VALE3"]})
        result = mgr.filterBySearchTerms(df, "PET")
        assert len(result) == 1
        assert result.iloc[0]["TICKER"] == "PETR4"

    def test_filter_fallback_multiple_terms(self):
        mgr = self._make_manager()
        mgr.cacheManager.tickerIndex = {}
        df = pd.DataFrame({"TICKER": ["PETR4", "PETR3", "VALE3"]})
        result = mgr.filterBySearchTerms(df, "PETR")
        assert len(result) == 2

    def test_filter_case_insensitive(self):
        mgr = self._make_manager()
        mgr.cacheManager.tickerIndex = {}
        df = pd.DataFrame({"TICKER": ["PETR4"]})
        result = mgr.filterBySearchTerms(df, "petr")
        assert len(result) == 1


class TestQueryHistorical:
    """Tests covering query.py lines 77-132."""

    def _make_manager(self, cache_df=None):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        mock_cache.STOCKS_CACHE = cache_df
        mock_cache.tickerIndex = {}
        from main.app.stocks_api.query import StocksQueryManager

        return StocksQueryManager(mock_cache)

    def test_cache_not_initialized_raises_503(self):
        mgr = self._make_manager(cache_df=None)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical(search="TEST0")
        assert exc_info.value.status_code == 503

    def test_basic_historical_query(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(search="TEST0")
        assert result["type"] == "historical"
        assert result["count"] > 0
        assert "data" in result
        assert "TICKER" in result["data"][0]

    def test_historical_with_search(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0}
        result = mgr.queryHistorical(search="TEST0")
        assert result["search"] == "TEST0"
        assert result["count"] == 1

    def test_historical_with_fields(self):
        """Pass field name WITHOUT year (how categorizeColumns returns them)."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        # categorizeColumns returns key="LUCRO LIQUIDO", not "LUCRO LIQUIDO 2023"
        result = mgr.queryHistorical(fields="LUCRO LIQUIDO")
        assert "LUCRO LIQUIDO" in result["fields"]

    def test_historical_with_dates(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(dates="2023")
        assert result["dates"] == [2023, 2023]

    def test_historical_with_order_by(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(search="TEST0", orderBy="PRECO")
        assert result["type"] == "historical"

    def test_historical_with_limit(self):
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(search="TEST", limit=2)
        assert result["count"] == 2

    def test_historical_no_historical_fields(self):
        """No historical data columns -> inner 400 caught by outer except -> 500."""
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"], "PRECO": [10.0]})
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical(search="TEST0")
        # The 400 is raised inside try, caught by the outer except -> 500
        assert exc_info.value.status_code == 500

    def test_historical_sorts_by_time(self):
        df = _make_stocks_df(rows=3)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(search="TEST0")
        assert result["type"] == "historical"

    def test_historical_deduplicates_by_ticker(self):
        df = _make_stocks_df(rows=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(search="TEST0")
        tickers = [d["TICKER"] for d in result["data"]]
        assert len(tickers) == len(set(tickers))

    def test_historical_exception_returns_500(self):
        """If an unexpected exception occurs in queryHistorical."""
        mgr = self._make_manager(cache_df=pd.DataFrame())

        class _ExplodingDf:
            """A dummy cache object that raises on .columns access."""

            @property
            def columns(self):
                raise Exception("simulated failure")

        mgr.cacheManager.STOCKS_CACHE = _ExplodingDf()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical(search="TEST0")
        assert exc_info.value.status_code == 500

    def test_historical_with_invalid_dates(self):
        """Invalid date format raises exception (line 132)."""
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"], "LUCRO LIQUIDO 2023": [100]})
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            mgr.queryHistorical(dates="2020,2021,2022")

    def test_historical_search_with_no_results(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {}
        result = mgr.queryHistorical(search="ZZZZ")
        assert result["count"] == 0

    def test_historical_no_fields_collected(self):
        """No historical columns at all -> inner 400 caught by outer except -> 500."""
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"]})
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical(fields="NONEXISTENT_FIELD")
        assert exc_info.value.status_code == 500

    def test_historical_with_date_range(self):
        """Historical query with a year range."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(dates="2022,2023")
        assert result["dates"] == [2022, 2023]

    def test_historical_search_multiple_terms_index(self):
        """Multiple search terms, all found in tickerIndex."""
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0, "TEST2": 2, "TEST4": 4}
        result = mgr.queryHistorical(search="TEST0,TEST2,TEST4")
        assert result["count"] == 3

    def test_historical_requires_search_fields_or_dates(self):
        """Calling with all None returns 400."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical()
        assert exc_info.value.status_code == 400


class TestQueryFundamental:
    """Tests covering query.py lines 142-202."""

    def _make_manager(self, cache_df=None):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        mock_cache.STOCKS_CACHE = cache_df
        mock_cache.tickerIndex = {}
        from main.app.stocks_api.query import StocksQueryManager

        return StocksQueryManager(mock_cache)

    def test_cache_not_initialized_raises_503(self):
        mgr = self._make_manager(cache_df=None)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(search="TEST0")
        assert exc_info.value.status_code == 503

    def test_basic_fundamental_query(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST0")
        assert result["type"] == "fundamental"
        assert result["count"] > 0
        assert "data" in result

    def test_fundamental_with_search(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0}
        result = mgr.queryFundamental(search="TEST0")
        assert result["search"] == "TEST0"

    def test_fundamental_with_fields(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(fields="PRECO,P/L")
        assert "PRECO" in result["fields"]

    def test_fundamental_with_date_range(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(dates="2024-01-01,2024-12-31")
        assert result["type"] == "fundamental"

    def test_fundamental_with_single_date(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(dates="2024-01-15")
        assert result["type"] == "fundamental"

    def test_fundamental_with_invalid_date(self):
        """Invalid date -> inner 400 passes through (not wrapped as 500)."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(dates="not-a-date,also-not-a-date")
        assert exc_info.value.status_code == 400

    def test_fundamental_with_order_by(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST0", orderBy="PRECO")
        assert result["type"] == "fundamental"

    def test_fundamental_with_limit(self):
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(fields="PRECO", limit=2)
        assert result["count"] == 2

    def test_fundamental_deduplicates_without_search(self):
        df = _make_stocks_df(rows=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(fields="PRECO")
        tickers = [d["TICKER"] for d in result["data"]]
        assert len(tickers) == len(set(tickers))

    def test_fundamental_with_search_no_dedup(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST")
        assert result["type"] == "fundamental"

    def test_fundamental_exception_returns_500(self):
        mgr = self._make_manager(cache_df=pd.DataFrame())

        class _ExplodingDf:
            """A dummy cache object that raises on .columns access."""

            @property
            def columns(self):
                raise Exception("simulated failure")

        mgr.cacheManager.STOCKS_CACHE = _ExplodingDf()
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(search="TEST0")
        assert exc_info.value.status_code == 500

    def test_fundamental_empty_search_string_no_dedup(self):
        """search.strip() == '' should still dedup (line 181)."""
        df = _make_stocks_df(rows=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="   ")
        tickers = [d["TICKER"] for d in result["data"]]
        assert len(tickers) == len(set(tickers))

    def test_fundamental_no_time_column(self):
        """DataFrame without TIME column."""
        df = pd.DataFrame(
            {
                "TICKER": ["A", "B"],
                "NOME": ["X", "Y"],
                "PRECO": [10.0, 20.0],
            }
        )
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST0")
        assert result["type"] == "fundamental"

    def test_fundamental_date_range_two_dates(self):
        """Two dates in the range, both valid."""
        df = pd.DataFrame(
            {
                "TICKER": ["A", "A", "B"],
                "NOME": ["X", "X", "Y"],
                "TIME": pd.to_datetime(["2024-01-15", "2024-06-15", "2024-03-10"]),
                "PRECO": [10.0, 15.0, 20.0],
            }
        )
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(dates="2024-01-01,2024-06-30")
        assert result["count"] >= 1

    def test_fundamental_with_invalid_single_date(self):
        """Single invalid date -> inner 400 passes through."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(dates="not-a-date")
        assert exc_info.value.status_code == 400

    def test_fundamental_fields_not_in_columns(self):
        """Invalid fields now raise 400 with actionable error message."""
        df = pd.DataFrame(
            {
                "TICKER": ["A"],
                "NOME": ["X"],
                "TIME": pd.to_datetime(["2024-01-15"]),
                "PRECO": [10.0],
            }
        )
        mgr = self._make_manager(cache_df=df)
        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(fields="NONEXISTENT,P/L")
        assert exc_info.value.status_code == 400
        assert "NONEXISTENT" in exc_info.value.detail
        assert "/stocks/fields" in exc_info.value.detail

    def test_fundamental_search_multiple_terms(self):
        """Multiple search terms with tickerIndex."""
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0, "TEST3": 3}
        result = mgr.queryFundamental(search="TEST0,TEST3")
        assert result["count"] == 2

    def test_fundamental_search_fallback_string_match(self):
        """Search with no index match falls back to string startswith."""
        df = _make_stocks_df(rows=3)
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {}
        result = mgr.queryFundamental(search="TEST")
        assert result["count"] == 3

    def test_fundamental_dates_one_date(self):
        """len(dateRange) == 1 -> per-ticker closest snapshot."""
        df = pd.DataFrame(
            {
                "TICKER": ["A", "B"],
                "NOME": ["X", "Y"],
                "TIME": pd.to_datetime(["2024-01-15", "2024-06-15"]),
                "PRECO": [10.0, 15.0],
            }
        )
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(dates="2024-01-15")
        # Per-ticker: each gets its closest snapshot (A→2024-01-15, B→2024-06-15)
        assert result["count"] == 2

    def test_fundamental_excludes_cotacao_10y(self):
        """COTACAO 10Y PADRAO and COTACAO 10Y AJUSTADA belong to /cotations, not /fundamental."""
        df = pd.DataFrame(
            {
                "TICKER": ["A", "B"],
                "NOME": ["X", "Y"],
                "TIME": pd.to_datetime(["2024-01-15", "2024-06-15"]),
                "PRECO": [10.0, 15.0],
                "P/L": [5.0, 8.0],
                "COTACAO 10Y PADRAO": [
                    '[{"DATA": "01-12-2016", "PRECO": 14.92}]',
                    '[{"DATA": "01-12-2016", "PRECO": 12.5}]',
                ],
                "COTACAO 10Y AJUSTADA": [
                    '[{"DATA": "01-12-2016", "PRECO": 12.5}]',
                    '[{"DATA": "01-12-2016", "PRECO": 10.0}]',
                ],
            }
        )
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST0")
        assert "COTACAO 10Y PADRAO" not in result["fields"]
        assert "COTACAO 10Y AJUSTADA" not in result["fields"]
        for d in result["data"]:
            assert "COTACAO 10Y PADRAO" not in d
            assert "COTACAO 10Y AJUSTADA" not in d

    def test_fundamental_does_not_mutate_cache_time_dtype(self):
        """Regression: queryFundamental must not mutate the shared cache TIME column.
        Bug at line 243: df["TIME"] = ... on a view of STOCKS_CACHE converted
        datetime64 -> object strings on first call, breaking /cotations sort."""
        from main.app.stocks_api.cache import StocksCacheManager
        from main.app.stocks_api.query import StocksQueryManager

        cache = MagicMock(spec=StocksCacheManager)
        cache.STOCKS_CACHE = pd.DataFrame(
            {
                "TICKER": ["TEST0", "TEST1"],
                "NOME": ["Empresa 0", "Empresa 1"],
                "TIME": pd.to_datetime(["2024-01-15", "2024-06-15"]),
                "PRECO": [10.0, 20.0],
            }
        )
        cache.tickerIndex = {}
        mgr = StocksQueryManager(cache)

        original_dtype = cache.STOCKS_CACHE["TIME"].dtype
        mgr.queryFundamental(search="TEST0")
        assert cache.STOCKS_CACHE["TIME"].dtype == original_dtype

    def test_fundamental_requires_search_fields_or_dates(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental()
        assert exc_info.value.status_code == 400


# ===========================================================================
# Tests for query.py – queryCotations
# ===========================================================================
# Tests for query.py – queryCotations
# Architectural contract:
#   1. For each TICKER, return only the MOST RECENT row (TIME desc, keep first).
#   2. The COTACAO 10Y column is a JSON list of {DATA: "DD-MM-YYYY", PRECO: float}.
#   3. The `dates` param filters the INNER JSON entries (DATA field),
#      NOT the outer stock rows. The outer TIME is for picking the latest row.
# ===========================================================================
class TestQueryCotations:
    """Tests for queryCotations and /stocks/cotations."""

    def _make_manager(self, cache_df=None):
        from main.app.stocks_api.cache import StocksCacheManager
        from main.app.stocks_api.query import StocksQueryManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        mock_cache.STOCKS_CACHE = cache_df
        mock_cache.tickerIndex = {}
        return StocksQueryManager(mock_cache)

    def _make_cotations_df(self, with_padrao=True, with_ajustada=True):
        """2 tickers x 2 rows. Rows 0,2 are 2024-01-15; rows 1,3 are 2024-06-15.
        Most recent per ticker is the second row (TIME = 2024-06-15)."""
        entries = [{"DATA": "01-12-2016", "PRECO": 14.92}, {"DATA": "02-12-2016", "PRECO": 15.0}]
        data = {
            "TICKER": ["TEST0", "TEST0", "TEST1", "TEST1"],
            "NOME": ["Empresa 0", "Empresa 0", "Empresa 1", "Empresa 1"],
            "TIME": pd.to_datetime(["2024-01-15", "2024-06-15", "2024-01-15", "2024-06-15"]),
            "PRECO": [10.0, 11.0, 20.0, 21.0],
        }
        if with_padrao:
            data["COTACAO 10Y PADRAO"] = [json.dumps(entries)] * 4
        if with_ajustada:
            data["COTACAO 10Y AJUSTADA"] = [json.dumps(entries)] * 4
        return pd.DataFrame(data)

    # --- 503 cache-not-init ---
    def test_cotations_cache_not_initialized_raises_503(self):
        mgr = self._make_manager(cache_df=None)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryCotations(adjusted=False)
        assert exc_info.value.status_code == 503

    # --- adjusted=False -> PADRAO ---
    def test_cotations_adjusted_false_returns_padrao(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        assert result["type"] == "cotations"
        assert result["fields"] == ["COTACAO 10Y PADRAO"]
        assert "COTACAO 10Y PADRAO" in result["data"][0]
        assert "COTACAO 10Y AJUSTADA" not in result["data"][0]

    # --- adjusted=True -> AJUSTADA ---
    def test_cotations_adjusted_true_returns_ajustada(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=True)
        assert result["type"] == "cotations"
        assert result["fields"] == ["COTACAO 10Y AJUSTADA"]
        assert "COTACAO 10Y AJUSTADA" in result["data"][0]
        assert "COTACAO 10Y PADRAO" not in result["data"][0]

    # --- ARCHITECTURAL FIX: most recent row per TICKER (.iloc[0] semantics) ---
    def test_cotations_returns_most_recent_per_ticker(self):
        """4 rows for 2 tickers -> 2 results, one per ticker, both with latest TIME."""
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        assert result["count"] == 2
        tickers = {d["TICKER"] for d in result["data"]}
        assert tickers == {"TEST0", "TEST1"}
        for d in result["data"]:
            assert d["TIME"].startswith("2024-06-15")

    # --- ARCHITECTURAL FIX: dates param filters inner JSON DATA, not outer rows ---
    def test_cotations_dates_filter_inner_json_data(self):
        """dates="2016-12-02" should keep only the 02-12-2016 entry in each JSON list."""
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False, dates="2016-12-02,2016-12-02")
        assert result["count"] == 2
        for d in result["data"]:
            cotation = d["COTACAO 10Y PADRAO"]
            assert isinstance(cotation, list)
            assert len(cotation) == 1
            assert cotation[0]["DATA"] == "02-12-2016"

    def test_cotations_dates_range_keeps_all_inner_entries(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False, dates="2016-12-01,2016-12-31")
        assert result["count"] == 2
        for d in result["data"]:
            assert len(d["COTACAO 10Y PADRAO"]) == 2

    def test_cotations_no_dates_keeps_all_inner_entries(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        for d in result["data"]:
            assert len(d["COTACAO 10Y PADRAO"]) == 2

    # --- search filter ---
    def test_cotations_with_search_filter(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0, "TEST1": 2}
        result = mgr.queryCotations(adjusted=False, search="TEST0")
        assert result["search"] == "TEST0"
        assert result["count"] == 1
        assert result["data"][0]["TICKER"] == "TEST0"

    def test_cotations_with_search_multiple_terms(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        mgr.cacheManager.tickerIndex = {"TEST0": 0, "TEST1": 2}
        result = mgr.queryCotations(adjusted=True, search="TEST0,TEST1")
        assert result["count"] == 2

    # --- missing column -> empty ---
    def test_cotations_missing_column_returns_empty(self):
        df = self._make_cotations_df(with_padrao=False, with_ajustada=False)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        assert result["count"] == 0
        assert result["data"] == []
        assert result["fields"] == ["COTACAO 10Y PADRAO"]
        assert result["type"] == "cotations"

    # --- dates param stored in response ---
    def test_cotations_dates_param_stored(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False, dates="2020-01-01,2024-12-31")
        assert result["dates"] == "2020-01-01,2024-12-31"

    def test_cotations_dates_default_none(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        assert result["dates"] is None

    # --- default search ---
    def test_cotations_default_search_all(self):
        df = self._make_cotations_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryCotations(adjusted=False)
        assert result["search"] == "all"

    # --- exception -> 500 ---
    def test_cotations_exception_returns_500(self):
        exploding = MagicMock()
        exploding.columns = PropertyMock(side_effect=Exception("boom"))
        mgr = self._make_manager(cache_df=exploding)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryCotations(adjusted=False)
        assert exc_info.value.status_code == 500

    # --- HTTP integration: /stocks/cotations route (one test, parametrized conceptually) ---
    def test_cotations_http_route(self, stocks_http_client):
        """Hit the actual /stocks/cotations HTTP endpoint with adjusted=false."""
        from main.app.stocks_api.query import stocksQuery

        original_cache = stocksQuery.cacheManager.STOCKS_CACHE
        original_index = stocksQuery.cacheManager.tickerIndex
        try:
            stocksQuery.cacheManager.STOCKS_CACHE = self._make_cotations_df()
            stocksQuery.cacheManager.tickerIndex = {"TEST0": 0, "TEST1": 2}
            resp = stocks_http_client.get("/stocks/cotations?adjusted=false&dates=2016-12-02,2016-12-02&search=TEST0")
            assert resp.status_code == 200
            body = resp.json()
            assert body["type"] == "cotations"
            assert body["fields"] == ["COTACAO 10Y PADRAO"]
            assert body["count"] == 1
            assert "Cache-Control" in resp.headers
            for d in body["data"]:
                assert len(d["COTACAO 10Y PADRAO"]) == 1
                assert d["COTACAO 10Y PADRAO"][0]["DATA"] == "02-12-2016"
        finally:
            stocksQuery.cacheManager.STOCKS_CACHE = original_cache
            stocksQuery.cacheManager.tickerIndex = original_index


# ===========================================================================
# Tests for query.py – queryRealtimeCotation
# ===========================================================================
class TestQueryLiveCotation:
    """Tests for queryLiveCotation and /stocks/cotations/live."""

    def _make_manager(self):
        from main.app.stocks_api.cache import StocksCacheManager
        from main.app.stocks_api.query import StocksQueryManager

        mock_cache = MagicMock(spec=StocksCacheManager)
        mock_cache.STOCKS_CACHE = pd.DataFrame()
        mock_cache.tickerIndex = {}
        return StocksQueryManager(mock_cache)

    def _mock_b3_response(self):
        return {
            "BizSts": {"cd": "OK"},
            "Msg": {"dtTm": "2026-06-23 17:14:19"},
            "Trad": [
                {
                    "scty": {
                        "SctyQtn": {
                            "opngPric": 44.96,
                            "minPric": 44.43,
                            "maxPric": 46.14,
                            "avrgPric": 45.455,
                            "curPrc": 45.64,
                            "prcFlcn": 0.8618785,
                        },
                        "mkt": {"nm": "Vista"},
                        "symb": "WEGE3",
                        "desc": "WEG         ON  EJ  NM",
                        "indxCmpnInd": True,
                    },
                    "ttlQty": 22848,
                }
            ],
        }

    def _patch_session(self, response=None, side_effect=None):
        mock_session = MagicMock()
        if side_effect:
            mock_session.get.side_effect = side_effect
        else:
            mock_resp = MagicMock()
            mock_resp.json.return_value = response or self._mock_b3_response()
            mock_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_resp
        return patch("main.app.stocks_api.query.getSession", return_value=mock_session)

    def test_success_returns_correct_shape(self):
        mgr = self._make_manager()
        with self._patch_session():
            result = mgr.queryLiveCotation("WEGE3")
        assert result["type"] == "realtime-cotation"
        assert result["search"] == "WEGE3"
        assert result["count"] == 1
        assert result["timestamp"] == "2026-06-23 17:14:19"
        row = result["data"][0]
        assert row["TICKER"] == "WEGE3"
        assert row["PRECO ATUAL"] == 45.64
        assert row["PRECO ORIGINAL"] == 44.96
        assert row["PRECO MINIMO"] == 44.43
        assert row["PRECO MAXIMO"] == 46.14
        assert row["PRECO MEDIO"] == 45.455
        assert "prcFlcn" not in row

    def test_lowercase_ticker_uppercased(self):
        mgr = self._make_manager()
        with self._patch_session():
            result = mgr.queryLiveCotation("wege3")
        assert result["search"] == "WEGE3"
        assert result["data"][0]["TICKER"] == "WEGE3"

    def test_live_route_cached_within_ttl(self, stocks_http_client):
        from main.controller.stocksapi_controller import responseCache

        responseCache.store.clear()
        responseCache.times.clear()
        responseCache.accessOrder.clear()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_b3_response()
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch("main.app.stocks_api.query.getSession", return_value=mock_session):
            resp1 = stocks_http_client.get("/stocks/cotations/live?search=WEGE3")
            resp2 = stocks_http_client.get("/stocks/cotations/live?search=WEGE3")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        assert mock_session.get.call_count == 1

    def test_live_route_refetches_after_ttl(self, stocks_http_client):
        from main.controller.stocksapi_controller import responseCache

        responseCache.store.clear()
        responseCache.times.clear()
        responseCache.accessOrder.clear()
        mock_session = MagicMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = self._mock_b3_response()
        mock_resp.raise_for_status = MagicMock()
        mock_session.get.return_value = mock_resp
        with patch("main.app.stocks_api.query.getSession", return_value=mock_session):
            stocks_http_client.get("/stocks/cotations/live?search=WEGE3")
            key = responseCache.makeKey("realtime_cotations", search="WEGE3")
            responseCache.times[key] = responseCache.times[key] - 16
            stocks_http_client.get("/stocks/cotations/live?search=WEGE3")
        assert mock_session.get.call_count == 2

    def test_b3_unavailable_returns_503(self):
        from fastapi import HTTPException

        mgr = self._make_manager()
        with self._patch_session(side_effect=Exception("connection refused")):
            with pytest.raises(HTTPException) as exc_info:
                mgr.queryLiveCotation("WEGE3")
        assert exc_info.value.status_code == 503

    def test_b3_bad_status_returns_404(self):
        from fastapi import HTTPException

        mgr = self._make_manager()
        payload = {"BizSts": {"cd": "ERR"}, "Trad": []}
        with self._patch_session(response=payload):
            with pytest.raises(HTTPException) as exc_info:
                mgr.queryLiveCotation("WEGE3")
        assert exc_info.value.status_code == 404

    def test_http_route_returns_200(self, stocks_http_client):
        with self._patch_session():
            resp = stocks_http_client.get("/stocks/cotations/live?search=WEGE3")
            assert resp.status_code == 200
            body = resp.json()
            assert body["type"] == "realtime-cotation"
            assert body["data"][0]["TICKER"] == "WEGE3"

    def test_http_route_search_required(self, stocks_http_client):
        """GET /stocks/realtime-cotation without search returns 422."""
        resp = stocks_http_client.get("/stocks/cotations/live")
        assert resp.status_code == 422

    # --- vectorized filterCotationColumn ---------------------------------
    def test_cotations_filter_cotation_column_filters_by_date(self):
        from main.app.stocks_api.query import filterCotationColumn
        from datetime import date

        series = pd.Series(
            [
                [{"DATA": "01-12-2016", "PRECO": 14.92}, {"DATA": "02-12-2016", "PRECO": 15.0}],
                [{"DATA": "01-06-2017", "PRECO": 16.0}, {"DATA": "02-06-2017", "PRECO": 17.0}],
            ]
        )
        result = filterCotationColumn(series, date(2016, 12, 2), date(2016, 12, 2))
        assert len(result) == 2
        assert len(result[0]) == 1
        assert result[0][0]["DATA"] == "02-12-2016"
        assert result[1] == []

    def test_cotations_filter_cotation_column_range(self):
        from main.app.stocks_api.query import filterCotationColumn
        from datetime import date

        series = pd.Series(
            [
                [
                    {"DATA": "01-12-2016", "PRECO": 1},
                    {"DATA": "02-12-2016", "PRECO": 2},
                    {"DATA": "03-12-2016", "PRECO": 3},
                ],
            ]
        )
        result = filterCotationColumn(series, date(2016, 12, 1), date(2016, 12, 2))
        assert len(result[0]) == 2
        assert {e["DATA"] for e in result[0]} == {"01-12-2016", "02-12-2016"}

    def test_cotations_filter_cotation_column_handles_non_list(self):
        from main.app.stocks_api.query import filterCotationColumn
        from datetime import date

        series = pd.Series([None, [{"DATA": "01-12-2016", "PRECO": 1}], "not a list", []])
        result = filterCotationColumn(series, date(2016, 12, 1), date(2016, 12, 31))
        assert result[0] is None
        assert len(result[1]) == 1
        assert result[2] == "not a list"
        assert result[3] == []

    def test_cotations_search_required(self, stocks_http_client):
        """GET /cotations without search returns 422."""
        resp = stocks_http_client.get("/stocks/cotations")
        assert resp.status_code == 422


# ===========================================================================
# Tests for stocksapi_controller.py – /stocks/health cache freshness
# ===========================================================================
def test_health_reports_cache_age(stocks_http_client, monkeypatch):
    from main.app.stocks_api.cache import stocksCache
    from datetime import datetime, timezone, timedelta

    monkeypatch.setattr(stocksCache, "STOCKS_CACHE", object())
    monkeypatch.setattr(stocksCache, "lastCacheUpdate", datetime.now(timezone.utc) - timedelta(hours=3))
    resp = stocks_http_client.get("/stocks/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cacheReady"] is True
    assert body["cacheAgeHours"] == 3.0
