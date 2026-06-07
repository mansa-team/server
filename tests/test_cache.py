import pytest
import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import MagicMock
from collections import OrderedDict
from main.app.stocks_api.cache import StocksCacheManager, QUERY_CACHE_MAX_SIZE, COLUMN_VALIDATOR


class TestCacheLRUEviction:
    """Tests for StocksCacheManager queryCache LRU eviction."""

    def _make_manager(self):
        """Create a StocksCacheManager with a mock DB engine."""
        mock_engine = MagicMock()
        return StocksCacheManager(mock_engine, threading.Lock())

    def test_query_cache_starts_empty(self):
        mgr = self._make_manager()
        assert len(mgr.queryCache) == 0

    def test_query_cache_max_size_constant(self):
        assert QUERY_CACHE_MAX_SIZE == 32

    def test_lru_eviction_when_over_limit(self):
        mgr = self._make_manager()
        now = time.time()
        # Use putCache which triggers eviction
        for i in range(QUERY_CACHE_MAX_SIZE + 5):
            key = tuple([f"COL_{i}"])
            mgr.putCache(key, f"data_{i}", now)

        # Should have evicted the oldest entries
        assert len(mgr.queryCache) == QUERY_CACHE_MAX_SIZE

        # First 5 entries should have been evicted
        for i in range(5):
            key = tuple([f"COL_{i}"])
            assert key not in mgr.queryCache

        # Last 32 entries should remain
        for i in range(5, QUERY_CACHE_MAX_SIZE + 5):
            key = tuple([f"COL_{i}"])
            assert key in mgr.queryCache

    def test_move_to_end_on_cache_hit(self):
        mgr = self._make_manager()
        now = time.time()

        # Add 3 entries
        mgr.putCache(("A",), "data_a", now)
        mgr.putCache(("B",), "data_b", now)
        mgr.putCache(("C",), "data_c", now)

        # Access "A" — should move to end
        mgr.queryCache.move_to_end(("A",))

        # Now evict from left — "B" should be evicted first
        mgr.queryCache.popitem(last=False)
        assert ("A",) in mgr.queryCache
        assert ("B",) not in mgr.queryCache
        assert ("C",) in mgr.queryCache

    def test_clear_query_cache(self):
        mgr = self._make_manager()
        now = time.time()
        mgr.putCache(("A",), "data_a", now)
        mgr.putCache(("B",), "data_b", now)

        mgr.clearQueryCache()
        assert len(mgr.queryCache) == 0

    def test_none_columns_key_is_none(self):
        """When columns is None, cache key should be None."""
        columns = None
        cacheKey = tuple(columns) if columns else None
        assert cacheKey is None

    def test_columns_key_is_tuple(self):
        columns = ["TICKER", "NOME"]
        cacheKey = tuple(columns) if columns else None
        assert cacheKey == ("TICKER", "NOME")


class TestColumnValidator:
    def test_valid_column_names(self):
        assert COLUMN_VALIDATOR.match("TICKER")
        assert COLUMN_VALIDATOR.match("NOME")
        assert COLUMN_VALIDATOR.match("PRECO")
        assert COLUMN_VALIDATOR.match("OPEN_PRICE")
        assert COLUMN_VALIDATOR.match("VOL 12M")

    def test_invalid_column_names(self):
        assert not COLUMN_VALIDATOR.match("ticker; DROP TABLE")
        assert not COLUMN_VALIDATOR.match("col OR 1=1")
        assert not COLUMN_VALIDATOR.match("col`name")
        assert not COLUMN_VALIDATOR.match("col\nname")

    def test_empty_string(self):
        assert not COLUMN_VALIDATOR.match("")


class TestCacheTTLLogic:
    def _make_manager(self):
        mock_engine = MagicMock()
        return StocksCacheManager(mock_engine, threading.Lock())

    def test_expired_entry_detected(self):
        mgr = self._make_manager()
        old_time = time.time() - 600  # 10 minutes ago (TTL is 300s)
        mgr.putCache(("TEST",), "data", old_time)

        now = time.time()
        cacheKey = ("TEST",)
        assert cacheKey in mgr.queryCache
        cachedData, cached_time = mgr.queryCache[cacheKey]
        assert now - cached_time >= mgr.QUERY_CACHE_TTL

    def test_fresh_entry_detected(self):
        mgr = self._make_manager()
        now = time.time()
        mgr.putCache(("TEST",), "data", now)

        cacheKey = ("TEST",)
        cachedData, cached_time = mgr.queryCache[cacheKey]
        assert now - cached_time < mgr.QUERY_CACHE_TTL
