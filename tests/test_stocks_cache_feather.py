import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from main.app.stocks_api.cache import COMPRESS_COLS, StocksCacheManager, optimizeDtypes


def test_optimize_dtypes_skips_pyarrow_for_compress_cols():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "COTACAO 10Y PADRAO": ['{"DATA": "x"}', '{"DATA": "y"}'],
            "NOME": ["PETROBRAS", "VALE"],
        }
    )
    result = optimizeDtypes(df)
    assert str(result["COTACAO 10Y PADRAO"].dtype) == "object"
    assert str(result["NOME"].dtype) == "category"


def test_missing_feather_runs_loader_then_swaps(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    fake_df = pd.DataFrame({"TICKER": ["PETR4"]})
    calls = []
    monkeypatch.setattr(cache_mod.os.path, "exists", lambda p: False)
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: calls.append("run") or None)
    monkeypatch.setattr(cache_mod.pd, "read_feather", lambda p: fake_df)
    manager = cache_mod.StocksCacheManager(None, threading.Lock())
    manager.STOCKS_CACHE = None
    manager.getCachedStocks()
    assert calls == ["run"]
    assert manager.STOCKS_CACHE is fake_df
    assert manager.tickerIndex == {"PETR4": 0}
