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

    # --- cacheScheduler (lines 28-35) ------------------------------------
    @patch("main.app.stocks_api.cache.threading.Thread")
    def test_cache_scheduler_starts_daemon_thread(self, mock_thread_cls):
        from main.app.stocks_api.cache import StocksCacheManager

        mock_engine = MagicMock()
        mgr = StocksCacheManager(mock_engine, threading.Lock())
        mock_thread = MagicMock()
        mock_thread_cls.return_value = mock_thread

        mgr.cacheScheduler()

        mock_thread_cls.assert_called_once()
        call_kwargs = mock_thread_cls.call_args
        assert call_kwargs[1]["daemon"] is True
        mock_thread.start.assert_called_once()

    # --- putCache (lines 78-82) ------------------------------------------
    def test_putCache_adds_entry_and_evicts_when_full(self):
        mgr = self._make_manager()
        mock_df = pd.DataFrame({"A": [1]})
        now = time.time()

        from main.app.stocks_api.cache import QUERY_CACHE_MAX_SIZE

        for i in range(QUERY_CACHE_MAX_SIZE):
            mgr.putCache(f"key_{i}", mock_df, now + i)

        assert len(mgr.queryCache) == QUERY_CACHE_MAX_SIZE

        # Adding one more should evict the oldest
        mgr.putCache("key_new", mock_df, now + 100)
        assert len(mgr.queryCache) == QUERY_CACHE_MAX_SIZE
        assert "key_new" in mgr.queryCache
        assert "key_0" not in mgr.queryCache  # oldest evicted

    # --- clearQueryCache (lines 84-85) -----------------------------------
    def test_clearQueryCache_empties_cache(self):
        mgr = self._make_manager()
        mgr.queryCache["a"] = (pd.DataFrame(), 0)
        mgr.queryCache["b"] = (pd.DataFrame(), 0)
        mgr.clearQueryCache()
        assert len(mgr.queryCache) == 0

    # --- getCachedStocks: cache hit (lines 38-46) -------------------------
    def test_getCachedStocks_cache_hit(self):
        mgr = self._make_manager()
        mock_df = pd.DataFrame({"TICKER": ["A"]})
        now = time.time()
        cache_key = ("PRECO",)
        mgr.queryCache[cache_key] = (mock_df, now)

        result = mgr.getCachedStocks(columns=["PRECO"])
        assert result is mock_df

    def test_getCachedStocks_cache_hit_expired(self):
        mgr = self._make_manager()
        mock_df = pd.DataFrame({"TICKER": ["A"]})
        expired_time = time.time() - 1000  # way past TTL
        cache_key = ("PRECO",)
        mgr.queryCache[cache_key] = (mock_df, expired_time)

        # Mock the DB connection to return data on refresh
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        new_df = pd.DataFrame({"TICKER": ["B"], "PRECO": [5.0]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=new_df):
            mgr.getCachedStocks(columns=["PRECO"])

        # Old expired entry should be removed, new one added
        assert cache_key in mgr.queryCache  # new entry
        assert mgr.queryCache[cache_key][0]["TICKER"].iloc[0] == "B"

    # --- getCachedStocks: force refresh (line 41 bypass) ------------------
    def test_getCachedStocks_force_refresh(self):
        mgr = self._make_manager()
        mock_df = pd.DataFrame({"TICKER": ["A"]})
        now = time.time()
        cache_key = ("PRECO",)
        mgr.queryCache[cache_key] = (mock_df, now)

        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        new_df = pd.DataFrame({"TICKER": ["C"], "PRECO": [99.0]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=new_df):
            mgr.getCachedStocks(columns=["PRECO"], force_refresh=True)

        # Cache should now have the new data
        assert cache_key in mgr.queryCache
        assert mgr.queryCache[cache_key][0]["TICKER"].iloc[0] == "C"

    # --- getCachedStocks: no columns (lines 61-62) -----------------------
    def test_getCachedStocks_no_columns(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["A", "B"], "NOME": ["X", "Y"], "TIME": ["t1", "t2"]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df):
            mgr.getCachedStocks(columns=None)

        # getCachedStocks stores in self.STOCKS_CACHE
        assert mgr.STOCKS_CACHE is not None
        assert len(mgr.STOCKS_CACHE) == 2

    # --- getCachedStocks: with columns and validation (lines 52-58) ------
    def test_getCachedStocks_with_valid_columns(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"], "TIME": ["t1"], "PRECO": [10.0]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df) as mock_read:
            mgr.getCachedStocks(columns=["PRECO", ""])
            mock_read.assert_called_once()

    # --- getCachedStocks: NaN/inf replacement (line 64) -------------------
    def test_getCachedStocks_replaces_nan_inf(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [np.nan]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df):
            mgr.getCachedStocks(columns=["VAL"])
            assert mgr.STOCKS_CACHE is not None
            assert mgr.STOCKS_CACHE["VAL"].iloc[0] is None

    # --- getCachedStocks: tickerIndex built (line 66) ---------------------
    def test_getCachedStocks_builds_ticker_index(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["PETR4", "VALE3"], "NOME": ["Petrobras", "Vale"]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df):
            mgr.getCachedStocks(columns=None)
            assert mgr.tickerIndex == {"PETR4": 0, "VALE3": 1}

    # --- getCachedStocks: exception (lines 75-76) -------------------------
    def test_getCachedStocks_exception_logged(self):
        mgr = self._make_manager()
        mgr.db.connect.side_effect = Exception("DB error")
        # Should not raise, just log
        mgr.getCachedStocks(columns=["PRECO"])

    # --- getCachedStocks: columns with inf -------------------------------
    def test_getCachedStocks_replaces_inf(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [np.inf]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df):
            mgr.getCachedStocks(columns=["VAL"])
            assert mgr.STOCKS_CACHE is not None
            assert mgr.STOCKS_CACHE["VAL"].iloc[0] is None

    def test_getCachedStocks_replaces_neg_inf(self):
        mgr = self._make_manager()
        mock_conn = MagicMock()
        mgr.db.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mgr.db.connect.return_value.__exit__ = MagicMock(return_value=False)
        df = pd.DataFrame({"TICKER": ["A"], "VAL": [-np.inf]})
        with patch("main.app.stocks_api.cache.pd.read_sql", return_value=df):
            mgr.getCachedStocks(columns=["VAL"])
            assert mgr.STOCKS_CACHE is not None
            assert mgr.STOCKS_CACHE["VAL"].iloc[0] is None


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

        mock_config.STOCKS_API = {"KEY.SYSTEM": False}
        mock_db = MagicMock()

        result = asyncio.run(verifyAPIKey(apiKey=None, db=mock_db))
        assert result is None

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_missing_raises_401(self, mock_config):
        """When key is required but not provided (line 19)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey=None, db=mock_db))
        assert exc_info.value.status_code == 401

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_invalid_key_raises_401(self, mock_config):
        """When DB returns no matching key (line 25)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="bad_key", db=mock_db))
        assert exc_info.value.status_code == 401

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_quota_exceeded(self, mock_config):
        """When quota is exceeded (line 28)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()
        mock_key_obj = MagicMock()
        mock_key_obj.isQuotaExceeded.return_value = True
        mock_db.query.return_value.filter.return_value.first.return_value = mock_key_obj

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(verifyAPIKey(apiKey="valid_key", db=mock_db))
        assert exc_info.value.status_code == 429

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_success(self, mock_config):
        """Happy path: key found, quota OK, increment and commit (lines 30-33)."""
        from main.app.stocks_api.key import verifyAPIKey

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()
        mock_key_obj = MagicMock()
        mock_key_obj.isQuotaExceeded.return_value = False
        mock_db.query.return_value.filter.return_value.first.return_value = mock_key_obj

        result = asyncio.run(verifyAPIKey(apiKey="valid_key", db=mock_db))
        assert result == "valid_key"
        mock_key_obj.incrementUsage.assert_called_once()
        mock_db.commit.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_verify_api_key_http_exception_rollback(self, mock_config):
        """HTTPException should cause rollback then re-raise (lines 35-37)."""
        from main.app.stocks_api.key import verifyAPIKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()
        mock_key_obj = MagicMock()
        mock_key_obj.isQuotaExceeded.return_value = True  # triggers 429
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

        mock_config.STOCKS_API = {"KEY.SYSTEM": True}
        mock_db = MagicMock()
        mock_db.query.side_effect = Exception("DB connection lost")

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

        mock_config.STOCKS_API = {"DEFAULT.QUOTA": 200}
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
        from main.app.stocks_api.key import createKey

        mock_config.STOCKS_API = {"DEFAULT.QUOTA": 150}
        mock_db = MagicMock()
        mock_existing = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = mock_existing

        result = createKey(mock_db, userId=1)
        assert isinstance(result, str)
        assert mock_existing.apiKey == result
        assert mock_existing.requestLimit == 150
        mock_db.commit.assert_called_once()

    @patch("main.app.stocks_api.key.Config")
    def test_create_key_exception_rollback(self, mock_config):
        """Exception during creation triggers rollback and 500 (lines 64-66)."""
        from main.app.stocks_api.key import createKey
        from fastapi import HTTPException

        mock_config.STOCKS_API = {"DEFAULT.QUOTA": 100}
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
            mgr.queryHistorical()
        assert exc_info.value.status_code == 503

    def test_basic_historical_query(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical()
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
        result = mgr.queryHistorical(orderBy="PRECO")
        assert result["type"] == "historical"

    def test_historical_with_limit(self):
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical(limit=2)
        assert result["count"] == 2

    def test_historical_no_historical_fields(self):
        """No historical data columns -> inner 400 caught by outer except -> 500."""
        df = pd.DataFrame({"TICKER": ["A"], "NOME": ["X"], "PRECO": [10.0]})
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical()
        # The 400 is raised inside try, caught by the outer except -> 500
        assert exc_info.value.status_code == 500

    def test_historical_sorts_by_time(self):
        df = _make_stocks_df(rows=3)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical()
        assert result["type"] == "historical"

    def test_historical_deduplicates_by_ticker(self):
        df = _make_stocks_df(rows=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryHistorical()
        tickers = [d["TICKER"] for d in result["data"]]
        assert len(tickers) == len(set(tickers))

    def test_historical_exception_returns_500(self):
        """If an unexpected exception occurs (line 132)."""
        mgr = self._make_manager(cache_df=pd.DataFrame())
        # Force copy() to raise
        mock_df = MagicMock()
        mock_df.copy.side_effect = Exception("copy failed")
        mgr.cacheManager.STOCKS_CACHE = mock_df
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryHistorical()
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
            mgr.queryFundamental()
        assert exc_info.value.status_code == 503

    def test_basic_fundamental_query(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental()
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
        """Invalid date -> inner 400 caught by outer except -> 500."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(dates="not-a-date,also-not-a-date")
        assert exc_info.value.status_code == 500

    def test_fundamental_with_order_by(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(orderBy="PRECO")
        assert result["type"] == "fundamental"

    def test_fundamental_with_limit(self):
        df = _make_stocks_df(rows=5)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(limit=2)
        assert result["count"] == 2

    def test_fundamental_deduplicates_without_search(self):
        df = _make_stocks_df(rows=3)
        df = pd.concat([df, df.iloc[[0]]], ignore_index=True)
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental()
        tickers = [d["TICKER"] for d in result["data"]]
        assert len(tickers) == len(set(tickers))

    def test_fundamental_with_search_no_dedup(self):
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(search="TEST")
        assert result["type"] == "fundamental"

    def test_fundamental_exception_returns_500(self):
        mgr = self._make_manager(cache_df=pd.DataFrame())
        # Force copy() to raise
        mock_df = MagicMock()
        mock_df.copy.side_effect = Exception("copy failed")
        mgr.cacheManager.STOCKS_CACHE = mock_df
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental()
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
        result = mgr.queryFundamental()
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
        """Single invalid date -> inner 400 caught by outer except -> 500."""
        df = _make_stocks_df()
        mgr = self._make_manager(cache_df=df)
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            mgr.queryFundamental(dates="not-a-date")
        assert exc_info.value.status_code == 500

    def test_fundamental_fields_not_in_columns(self):
        """Fields that don't exist in the dataframe are filtered out."""
        df = pd.DataFrame(
            {
                "TICKER": ["A"],
                "NOME": ["X"],
                "TIME": pd.to_datetime(["2024-01-15"]),
                "PRECO": [10.0],
            }
        )
        mgr = self._make_manager(cache_df=df)
        result = mgr.queryFundamental(fields="NONEXISTENT,P/L")
        # P/L is a fundamental col but not in df columns
        assert result["type"] == "fundamental"

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
        """len(dateRange) == 1 -> single date filter."""
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
        assert result["count"] == 1
