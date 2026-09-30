import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pyarrow as pa
from pyarrow import feather

from main.app.stocks_api.cache import StocksCacheManager
from main.app.stocks_api.frame import PRESORTED_FLAG_KEY, optimizeDtypes


def test_optimize_dtypes_skips_pyarrow_for_compress_cols():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "COTACAO 10Y PADRAO": ['{"DATA": "x"}', '{"DATA": "y"}'],
            "NOME": ["PETROBRAS", "VALE"],
        }
    )
    result = optimizeDtypes(df)
    assert str(result["COTACAO 10Y PADRAO"].dtype) in ("object", "str")
    assert str(result["NOME"].dtype) == "category"


def test_missing_feather_runs_loader_then_swaps(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    fake_df = pd.DataFrame({"TICKER": ["PETR4"]})
    calls = []
    monkeypatch.setattr(cache_mod.os.path, "exists", lambda p: False)
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: calls.append("run") or None)
    monkeypatch.setattr(cache_mod, "readFeatherDataFrame", lambda p: (fake_df, False))
    manager = cache_mod.StocksCacheManager(None, threading.Lock())
    manager.STOCKS_CACHE = None
    manager.getCachedStocks()
    assert calls == ["run"]
    assert manager.STOCKS_CACHE is fake_df
    assert manager.tickerIndex == {"PETR4": 0}


def test_stale_feather_serves_snapshot_and_spawns_refresh(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.STALE_AFTER_SECONDS = 6 * 3600
    fake_df = pd.DataFrame({"TICKER": ["VALE3"]})
    fake_df.to_feather(cache_mod.CACHE_FEATHER_PATH)  # real file -> Path.exists() is genuinely True
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)  # never hit the real loader
    monkeypatch.setattr(cache_mod.os.path, "getmtime", lambda p: 0.0)  # 1970 -> definitely stale
    monkeypatch.setattr(cache_mod.time, "time", lambda: 10.0 * 3600)  # 10h later
    monkeypatch.setattr(cache_mod, "readFeatherDataFrame", lambda p: (fake_df, False))
    spawned = []
    monkeypatch.setattr(
        cache_mod.threading.Thread,
        "start",
        lambda self: spawned.append((self._target.__name__, self._kwargs.get("force_refresh"))),
    )
    manager = cache_mod.StocksCacheManager(None, threading.Lock())
    manager.getCachedStocks()
    assert manager.STOCKS_CACHE is fake_df
    assert spawned == [("getCachedStocks", True)]


def test_fresh_feather_serves_snapshot_without_refresh(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.STALE_AFTER_SECONDS = 6 * 3600
    fake_df = pd.DataFrame({"TICKER": ["ITUB4"]})
    fake_df.to_feather(cache_mod.CACHE_FEATHER_PATH)  # real file, fresh mtime (now)
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)
    monkeypatch.setattr(cache_mod.os.path, "getmtime", lambda p: 10.0 * 3600 - 60)  # fresh
    monkeypatch.setattr(cache_mod.time, "time", lambda: 10.0 * 3600)
    monkeypatch.setattr(cache_mod, "readFeatherDataFrame", lambda p: (fake_df, False))
    spawned = []
    monkeypatch.setattr(
        cache_mod.threading.Thread,
        "start",
        lambda self: spawned.append(self._target.__name__),
    )
    manager = cache_mod.StocksCacheManager(None, threading.Lock())
    manager.getCachedStocks()
    assert manager.STOCKS_CACHE is fake_df
    assert spawned == []


def test_read_feather_dataframe_uses_arrow_backed_columns(tmp_path):
    import main.app.stocks_api.cache as cache_mod

    path = tmp_path / "cache.feather"
    feather.write_feather(
        pd.DataFrame({"TICKER": ["PETR4"], "NOME": ["PETROBRAS"], "PRECO": [1.5], "BLOB": [b"xy"]}), path
    )

    df, presorted = cache_mod.readFeatherDataFrame(path)

    assert presorted is False
    # pandas 3 defaults str columns to large_string[pyarrow] (PDEP-14); pandas 2 to string[pyarrow].
    # The property under test is "arrow-backed", not the arrow string width.
    assert isinstance(df["TICKER"].dtype, pd.ArrowDtype)
    assert pd.api.types.is_string_dtype(df["TICKER"].dtype)
    assert str(df["BLOB"].dtype) == "binary[pyarrow]"
    assert df["TICKER"].iloc[0] == "PETR4"
    assert df["BLOB"].iloc[0] == b"xy"


def test_read_feather_dataframe_detects_presorted_marker(tmp_path):
    import main.app.stocks_api.cache as cache_mod

    path = tmp_path / "cache.feather"
    table = pa.Table.from_pandas(
        pd.DataFrame({"TICKER": ["PETR4"], "TIME": [pd.Timestamp("2024-01-01")]}), preserve_index=False
    ).replace_schema_metadata({PRESORTED_FLAG_KEY: b"1"})
    with pa.OSFile(str(path), "wb") as sink, pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)

    df, presorted = cache_mod.readFeatherDataFrame(path)

    assert presorted is True
    assert df["TICKER"].iloc[0] == "PETR4"
