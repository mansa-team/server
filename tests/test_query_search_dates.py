"""Failing-first tests: exact search must not collapse stock snapshots."""

import threading
from unittest.mock import MagicMock

import pandas as pd

from main.app.stocks_api.cache import StocksCacheManager, buildTickerIndex
from main.app.stocks_api.query import filterBySearchTerms, queryFundamental


def make_multi_df():
    return pd.DataFrame(
        {
            "TICKER": ["PETR4", "PETR4", "PETR4", "VALE3"],
            "NOME": ["Petrobras PN"] * 3 + ["Vale ON"],
            "TIME": pd.to_datetime(["2024-01-15", "2024-02-15", "2024-03-15", "2024-01-15"]),
            "P/L": [5.0, 5.1, 5.2, 6.0],
            "COTACAO 10Y PADRAO": [10.0, 10.1, 10.2, 11.0],
        }
    )


def make_manager(df, index):
    manager = StocksCacheManager(MagicMock(), threading.Lock())
    manager.STOCKS_CACHE = df
    manager.tickerIndex = index
    return manager


def test_exact_search_returns_all_snapshot_rows():
    df = make_multi_df()
    manager = make_manager(df, buildTickerIndex(df))

    filtered = filterBySearchTerms(df, "PETR4", buildTickerIndex(df))

    assert filtered["TICKER"].tolist() == ["PETR4", "PETR4", "PETR4"]


def test_exact_search_with_dates_returns_matching_rows():
    df = make_multi_df()
    manager = make_manager(df, buildTickerIndex(df))

    result = queryFundamental(search="PETR4", fields="P/L", dates="2024-01-01,2024-02-15", cacheManager=manager)

    assert result["count"] == 2


def test_mixed_search_returns_exact_and_prefix():
    df = make_multi_df()
    manager = make_manager(df, buildTickerIndex(df))

    filtered = filterBySearchTerms(df, "PETR4,VALE", buildTickerIndex(df))

    assert set(filtered["TICKER"].tolist()) == {"PETR4", "VALE3"}


def test_trailing_comma_does_not_match_everything():
    df = make_multi_df()
    manager = make_manager(df, buildTickerIndex(df))

    filtered = filterBySearchTerms(df, "PETR4,", buildTickerIndex(df))

    assert filtered["TICKER"].tolist() == ["PETR4", "PETR4", "PETR4"]
