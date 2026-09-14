"""Deterministic tests for the paired (frame + tickerIndex) stocks cache snapshot."""

import threading
from unittest.mock import MagicMock

import pandas as pd
import pytest
from fastapi import HTTPException

from main.app.stocks_api.cache import StocksCacheManager
from main.app.stocks_api import query as queryModule
from main.app.stocks_api.query import filterBySearchTerms


def make_df(tickers):
    return pd.DataFrame(
        {
            "TICKER": tickers,
            "NOME": [f"Empresa {t}" for t in tickers],
            "TIME": pd.to_datetime(["2024-01-15"] * len(tickers)),
            "P/L": [5.0 + i for i in range(len(tickers))],
            "LUCRO LIQUIDO 2023": [100.0 + 10.0 * i for i in range(len(tickers))],
            "COTACAO 10Y PADRAO": [10.0 + i for i in range(len(tickers))],
        }
    )


def make_manager(df, index):
    manager = StocksCacheManager(MagicMock(), threading.Lock())
    manager.STOCKS_CACHE = df
    manager.tickerIndex = index
    return manager


def make_swapping_query(df_v1, idx_v1, df_v2, idx_v2):
    """Query manager whose snapshot() returns the v1 pair, then swaps the manager state to v2."""
    manager = make_manager(df_v1, idx_v1)
    originalSnapshot = manager.snapshot

    def swappingSnapshot():
        pair = originalSnapshot()
        manager.STOCKS_CACHE = df_v2
        manager.tickerIndex = idx_v2
        return pair

    manager.snapshot = swappingSnapshot
    return manager


class TestPairedSnapshot:
    def test_query_methods_filter_with_snapshot_pair_only(self):
        df_v1 = make_df(["AAA1", "BBB1"])
        idx_v1 = {"AAA1": 0, "BBB1": 1}
        df_v2 = make_df(["BBB1", "AAA1"])  # row order swapped: v1 index now points at wrong rows
        idx_v2 = {"AAA1": 1, "BBB1": 0}

        calls = (
            ("queryHistorical", {"search": "AAA1", "fields": "LUCRO LIQUIDO"}),
            ("queryFundamental", {"search": "AAA1", "fields": "P/L"}),
            ("queryCotations", {"search": "AAA1"}),
        )
        for methodName, kwargs in calls:
            manager = make_swapping_query(df_v1, idx_v1, df_v2, idx_v2)

            result = getattr(queryModule, methodName)(cacheManager=manager, **kwargs)

            assert result["data"][0]["TICKER"] == "AAA1", methodName
            # swap fired after the snapshot; the result must still be built from the v1 pair
            assert manager.STOCKS_CACHE is df_v2, methodName
            assert manager.tickerIndex is idx_v2, methodName

    def test_query_raises_503_against_snapshot_frame_not_post_swap_state(self):
        df_v2 = make_df(["AAA1"])
        manager = make_swapping_query(None, {}, df_v2, {"AAA1": 0})

        with pytest.raises(HTTPException) as excinfo:
            queryModule.queryCotations(search="AAA1", cacheManager=manager)
        assert excinfo.value.status_code == 503


class TestFilterBySearchTermsIndex:
    def test_passed_index_wins_over_manager_global(self):
        df = make_df(["AAA1", "BBB1"])
        manager = make_manager(df, {"AAA1": 1})  # decoy global: points AAA1 at the BBB1 row

        filtered = filterBySearchTerms(df, "AAA1", {"AAA1": 0})

        assert filtered["TICKER"].tolist() == ["AAA1"]

    def test_explicit_manager_index_used(self):
        df = make_df(["AAA1", "BBB1"])
        manager = make_manager(df, {"AAA1": 1})

        filtered = filterBySearchTerms(df, "AAA1", manager.tickerIndex)

        assert filtered["TICKER"].tolist() == ["AAA1"]
