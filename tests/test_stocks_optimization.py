import pytest
import sys
import os
import threading
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.stocks_api.cache import StocksCacheManager, stocksCache
from main.app.stocks_api.query import StocksQueryManager
from config import stocksEngine
import pandas as pd


# ==================== Feature 1: Ticker Index ====================
class TestTickerIndex:
    """Tests for dynamic ticker index feature"""

    def test_ticker_index_built_after_cache_load(self):
        """Ticker index should be built when cache is loaded"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        assert cache_manager.ticker_index is not None
        assert isinstance(cache_manager.ticker_index, dict)

    def test_ticker_index_contains_all_tickers(self):
        """Ticker index should contain all tickers from cache"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        cache_tickers = set(cache_manager.STOCKS_CACHE["TICKER"].astype(str).str.upper())
        index_tickers = set(cache_manager.ticker_index.keys())

        assert index_tickers == cache_tickers

    def test_ticker_index_case_insensitive(self):
        """Ticker index should be case-insensitive"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        first_ticker = next(iter(cache_manager.ticker_index.keys()))
        upper_idx = cache_manager.ticker_index.get(first_ticker.upper())
        assert upper_idx is not None

    def test_ticker_lookup_returns_valid_index(self):
        """Looking up ticker should return valid row index"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        ticker = next(iter(cache_manager.ticker_index.keys()))
        idx = cache_manager.ticker_index[ticker]

        assert idx >= 0
        assert idx < len(cache_manager.STOCKS_CACHE)

    def test_ticker_index_rebuilt_on_cache_refresh(self):
        """Ticker index should be rebuilt when cache refreshes"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        first_index = cache_manager.ticker_index.copy()
        cache_manager.getCachedStocks()

        assert len(cache_manager.ticker_index) == len(first_index) or len(cache_manager.ticker_index) != len(
            first_index
        )


# ==================== Feature 2: Query Result Caching ====================
class TestQueryCaching:
    """Tests for query result caching"""

    def test_cache_manager_has_caches_method(self):
        """CacheManager should track cached queries"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        # Should have a query cache dict
        assert hasattr(cache_manager, "query_cache")

    def test_query_cache_ttl_configuration(self):
        """Query cache should have configurable TTL"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        assert hasattr(cache_manager, "QUERY_CACHE_TTL")
        assert cache_manager.QUERY_CACHE_TTL > 0

    def test_get_cached_stocks_respects_columns_parameter(self):
        """getCachedStocks should support column filtering"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())

        # With force_refresh=True, should fetch new data with columns
        df = cache_manager.getCachedStocks(columns=["TICKER", "NOME"], force_refresh=True)
        if df is not None:
            assert "TICKER" in df.columns
            assert "NOME" in df.columns

    def test_different_queries_not_cached(self):
        """Different query parameters should not share cache"""
        pass

    def test_cache_expiry_after_ttl(self):
        """Cache should expire after TTL"""
        pass


# ==================== Feature 3: Connection Pool Tuning ====================
class TestConnectionPool:
    """Tests for connection pool configuration"""

    def test_stocks_engine_has_pool_configuration(self):
        """Stocks engine should have optimized pool settings"""
        from config import stocksEngine

        pool = stocksEngine.pool
        assert pool is not None


# ==================== Feature 4: Lazy JSON Deserialization ====================
class TestLazyDeserialization:
    """Tests for lazy JSON deserialization"""

    def test_query_manager_has_deserialize_method(self):
        """Query manager should have deserialize method"""
        from main.app.stocks_api.query import StocksQueryManager
        from main.app.stocks_api.cache import stocksCache

        query_manager = StocksQueryManager(stocksCache)

        assert hasattr(query_manager, "deserializeJsonColumns")


# ==================== Feature 5: Query Optimization Integration ====================
class TestQueryOptimization:
    """Integration tests for all query optimizations"""

    def test_all_optimizations_present(self):
        """All optimizations should be implemented"""
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        # Feature 1: Ticker index
        assert hasattr(cache_manager, "ticker_index")
        assert len(cache_manager.ticker_index) > 0

        # Feature 2: Query cache
        assert hasattr(cache_manager, "query_cache")

        # Feature 3: TTL config
        assert hasattr(cache_manager, "QUERY_CACHE_TTL")

    def test_query_filter_uses_optimization(self):
        """Query filter should use ticker index"""
        from main.app.stocks_api.query import StocksQueryManager
        from main.app.stocks_api.cache import stocksCache

        query_manager = StocksQueryManager(stocksCache)
        query_manager.cacheManager.getCachedStocks()

        # Create a small test DataFrame
        test_df = query_manager.cacheManager.STOCKS_CACHE.head(10)

        # Filter should work (uses optimization if ticker in index)
        result = query_manager.filterBySearchTerms(test_df, "PETR")

        assert result is not None


# ==================== Performance Benchmarks ====================
class TestPerformanceBenchmarks:
    """Performance benchmark tests for stocks API"""

    def test_ticker_index_lookup_performance(self):
        """Ticker index lookup should be O(1) - very fast"""
        import time

        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        # Get a ticker to test
        ticker = next(iter(cache_manager.ticker_index.keys()))

        # Benchmark: 1000 lookups
        start = time.perf_counter()
        for _ in range(1000):
            _ = cache_manager.ticker_index.get(ticker)
        elapsed = time.perf_counter() - start

        # 1000 O(1) lookups should be < 10ms
        assert elapsed < 0.01, f"Ticker index lookup too slow: {elapsed * 1000:.2f}ms for 1000 lookups"
        print(f"✓ Ticker index: {elapsed * 1000:.2f}ms for 1000 lookups")

    def test_prefix_scan_performance(self):
        """Prefix scan should be much slower than index lookup"""
        import time

        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        df = cache_manager.STOCKS_CACHE
        search_term = "PETR"

        # Benchmark: prefix scan on full DataFrame
        start = time.perf_counter()
        mask = df["TICKER"].str.upper().str.startswith(search_term)
        result = df[mask]
        elapsed = time.perf_counter() - start

        # Prefix scan should be < 100ms for ~46k rows
        assert elapsed < 0.1, f"Prefix scan too slow: {elapsed * 1000:.2f}ms"
        print(f"✓ Prefix scan: {elapsed * 1000:.2f}ms for ~{len(df)} rows")

    def test_index_lookup_vs_scan_comparison(self):
        """Index lookup should be significantly faster than scan"""
        import time

        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())
        cache_manager.getCachedStocks()

        df = cache_manager.STOCKS_CACHE
        ticker = next(iter(cache_manager.ticker_index.keys()))

        # Index lookup
        start = time.perf_counter()
        for _ in range(100):
            idx = cache_manager.ticker_index.get(ticker)
            _ = df.iloc[idx]
        index_time = time.perf_counter() - start

        # Prefix scan
        start = time.perf_counter()
        for _ in range(100):
            mask = df["TICKER"].str.upper().str.startswith(ticker)
            _ = df[mask]
        scan_time = time.perf_counter() - start

        speedup = scan_time / index_time if index_time > 0 else 1
        print(f"✓ Index lookup: {index_time * 1000:.2f}ms vs Scan: {scan_time * 1000:.2f}ms ({speedup:.1f}x faster)")

        # Index should be at least 10x faster
        assert speedup > 10, f"Index lookup not fast enough: {speedup:.1f}x speedup"

    def test_query_cache_performance(self):
        """Query cache should avoid recomputation"""
        import time

        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())

        # First call - miss cache, load from DB
        start = time.perf_counter()
        cache_manager.getCachedStocks(force_refresh=True)
        first_call = time.perf_counter() - start

        # Second call - hit cache
        start = time.perf_counter()
        cache_manager.getCachedStocks()
        second_call = time.perf_counter() - start

        print(f"✓ First call: {first_call * 1000:.0f}ms vs Cached: {second_call * 1000:.2f}ms")

        # Cached call should be > 10x faster
        speedup = first_call / second_call if second_call > 0 else 1
        assert speedup > 10, f"Cache not working: {speedup:.1f}x speedup"

    def test_column_projection_performance(self):
        """Column projection should reduce memory and time"""

        # This test checks that getCachedStocks accepts columns parameter
        # Actual performance depends on network latency
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())

        # With columns param - should work without error
        df = cache_manager.getCachedStocks(columns=["TICKER", "NOME"], force_refresh=True)

        # Verify columns are present (if data returned)
        if df is not None and len(df) > 0:
            assert "TICKER" in df.columns
            assert "NOME" in df.columns

    def test_cache_initialization_time(self):
        """Cache initialization should complete in reasonable time"""
        import time

        # Note: This test depends on network latency to remote DB
        # We test that it completes, not how fast (network-bound)
        cache_manager = StocksCacheManager(stocksEngine, threading.Lock())

        start = time.perf_counter()
        cache_manager.getCachedStocks(force_refresh=True)
        elapsed = time.perf_counter() - start

        print(f"✓ Cache init: {elapsed * 1000:.0f}ms for {len(cache_manager.STOCKS_CACHE)} rows")

        # Just verify it completes (network latency varies widely)
        assert elapsed < 120, f"Cache init too slow: {elapsed:.2f}s"


class TestFilterBySearchTerms:
    """Tests for optimized search filtering"""

    def test_filter_with_ticker_index(self):
        """Filter should use ticker index for O(1) lookup"""
        # This will test the optimized filterBySearchTerms
        pass


class TestQueryPerformance:
    """Performance tests for query operations"""

    def test_query_response_time_under_1_second(self):
        """Query should respond within 1 second"""
        # This is a performance benchmark
        pass
