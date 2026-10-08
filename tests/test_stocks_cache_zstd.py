import threading
import zstandard as zstd
from unittest.mock import MagicMock

import pytest
import pandas as pd
import pyarrow as pa
from pyarrow import feather

import main.app.stocks_api.build as build_mod
import main.app.stocks_api.cache as cache_mod
from main.app.stocks_api.cache import StocksCacheManager
from main.app.stocks_api.frame import PRESORTED_FLAG_KEY
from main.app.stocks_api.query import deserializeJsonColumns, filterCotationColumn
from main.app.stocks_api.util import detectNestedFields
from main.app.stocks_api.compress import getNest, rebuildAbbrevs


class FakeResult:
    def __init__(self, frames):
        self.batches = [list(f.itertuples(index=False, name=None)) for f in frames]
        self.columns = list(frames[0].columns) if frames else []

    def keys(self):
        return self.columns

    def fetchmany(self, n):
        return self.batches.pop(0) if self.batches else []

    def fetchall(self):
        rows = []
        while self.batches:
            rows.extend(self.batches.pop(0))
        return rows


class FakeConn:
    def __init__(self, frames=None, col_types=None):
        self.frames = frames or []
        self.col_types = col_types or {}

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execution_options(self, **kw):
        return self

    def exec_driver_sql(self, sql):
        if "SHOW COLUMNS" in sql:
            typeDf = pd.DataFrame({"Field": list(self.col_types), "Type": list(self.col_types.values())})
            return FakeResult([typeDf])
        return FakeResult(self.frames)


class FakeEngine:
    def connect(self):
        return FakeConn()


@pytest.fixture(autouse=True)
def fakeStocksEngine(monkeypatch):
    monkeypatch.setattr(build_mod, "stocksEngine", FakeEngine())


def test_filter_cotation_column_filters_by_date_without_index():
    series = pd.Series(
        [
            [{"DATA": "01-01-2024", "PRECO": 10.0}, {"DATA": "15-06-2026", "PRECO": 11.0}],
            [{"DATA": "01-01-2024", "PRECO": 20.0}, {"DATA": "10-07-2026", "PRECO": 22.0}],
        ]
    )
    out = filterCotationColumn(series, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"))
    assert out.tolist() == [
        [{"DATA": "15-06-2026", "PRECO": 11.0}],
        [{"DATA": "10-07-2026", "PRECO": 22.0}],
    ]


def test_get_cached_stocks_does_not_build_date_index(monkeypatch, tmp_path):
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([df]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()
    assert not hasattr(m, "cotationDateIndex")


def test_get_cached_stocks_skips_build_when_another_process_holds_lock(monkeypatch, tmp_path):
    fcntl = pytest.importorskip("fcntl")
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([df]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()

    lockFile = open(tmp_path / "refresh.lock", "w")
    fcntl.flock(lockFile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        calls = []
        monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: calls.append(1))
        m = StocksCacheManager(None, threading.Lock())
        m.getCachedStocks(force_refresh=True)
        assert calls == []
    finally:
        lockFile.close()


def makeDf():
    return pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOME": ["PETROBRAS PN", "VALE ON"],
            "TIME": ["29-07-2026", "29-07-2026"],
            "COTACAO 10Y PADRAO": [
                '[{"DATA": "01-01-2024", "PRECO": 10.0}, {"DATA": "15-06-2026", "PRECO": 11.0}]',
                '[{"DATA": "01-01-2024", "PRECO": 20.0}, {"DATA": "10-07-2026", "PRECO": 22.0}]',
            ],
            "NOTICIAS": ['[{"TITULO": "a"}]', None],
        }
    )


def test_get_cached_stocks_compresses_jsoncolumns(monkeypatch, tmp_path):
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([makeDf()]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()
    df = m.STOCKS_CACHE
    assert isinstance(df["COTACAO 10Y PADRAO"].iloc[0], bytes)
    assert zstd.ZstdDecompressor().decompress(df["COTACAO 10Y PADRAO"].iloc[0]).decode("utf-8").startswith("[{")
    assert isinstance(df["NOTICIAS"].iloc[0], bytes)
    assert pd.isna(df["NOTICIAS"].iloc[1])  # ArrowDtype null cells are pd.NA


def test_get_cached_stocks_keeps_raw_nested_sample(monkeypatch, tmp_path):
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([makeDf()]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert nested["COTACAO 10Y PADRAO"].iloc[0].startswith("[{")


def test_nested_sample_skips_all_null_leading_rows(monkeypatch, tmp_path):
    empty = pd.DataFrame(
        {
            "TICKER": ["AAA1", "BBB2"],
            "NOME": ["x", "y"],
            "TIME": [None, None],
            "COTACAO 10Y PADRAO": [None, None],
            "NOTICIAS": [None, None],
        }
    )
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([empty, makeDf()]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert nested["COTACAO 10Y PADRAO"].iloc[0].startswith("[{")


def test_nested_sample_captures_sparsecolumns_across_chunks(monkeypatch, tmp_path):
    first = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOME": ["PETROBRAS PN", "VALE ON"],
            "COTACAO 10Y PADRAO": [
                '[{"DATA": "01-01-2024", "PRECO": 10.0}]',
                '[{"DATA": "01-01-2024", "PRECO": 20.0}]',
            ],
            "NOTICIAS": [None, None],
        }
    )
    later = pd.DataFrame(
        {
            "TICKER": ["WEGE3"],
            "NOME": ["WEG ON"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 30.0}]'],
            "NOTICIAS": ['[{"TITULO": "noticia", "LINK": "http://x"}]'],
        }
    )
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([first, later]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert isinstance(nested["NOTICIAS"].iloc[0], str)
    assert nested["NOTICIAS"].iloc[0].startswith("[{")


def test_build_null_first_chunk_numeric_column_uses_db_type(monkeypatch, tmp_path):
    """Regression: sparse NUMERIC columns (e.g. 'DIVIDENDOS 2027') that are
    all-None in the first chunk must be pinned to their DB type (float), not
    blindly widened to string — that broke later chunks with real values:
    pyarrow.lib.ArrowTypeError: ('Expected a string or bytes dtype, got
    float32', 'Conversion failed for column DIVIDENDOS 2027 with type
    float32')."""
    first = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOME": ["PETROBRAS PN", "VALE ON"],
            "DIVIDENDOS 2027": [None, None],
        }
    )
    later = pd.DataFrame(
        {
            "TICKER": ["WEGE3"],
            "NOME": ["WEG ON"],
            "DIVIDENDOS 2027": [1.25],
        }
    )
    conn = FakeConn([first, later], col_types={"DIVIDENDOS 2027": "double"})
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: conn)
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    df = pd.read_feather(cache_mod.CACHE_FEATHER_PATH)
    assert df["DIVIDENDOS 2027"].iloc[2] == 1.25
    assert str(df["DIVIDENDOS 2027"].dtype).startswith("float")


def test_detect_nested_fields_tolerates_loose_nan_json():

    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "HISTORICO DIVIDENDOS": ['[{"DATA COM": "01-01-2024", "VALOR ORIGINAL": NaN}]'],
        }
    )
    nest = detectNestedFields(df)
    assert "HISTORICO DIVIDENDOS" in nest
    assert set(nest["HISTORICO DIVIDENDOS"]["subfields"]) >= {"DATA COM", "VALOR ORIGINAL"}


def test_detect_nested_fields_skips_empty_array_head():

    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOTICIAS": ["[]", '[{"TITULO": "a", "LINK": "http://x"}]'],
        }
    )
    nest = detectNestedFields(df)
    assert "NOTICIAS" in nest
    assert set(nest["NOTICIAS"]["subfields"]) >= {"TITULO", "LINK"}


def test_deserialize_jsoncolumns_decompresses_bytes():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "COTACAO 10Y PADRAO": [zstd.ZstdCompressor(level=3).compress(b'[{"DATA": "01-01-2024", "PRECO": 10.0}]')],
        }
    )
    out = deserializeJsonColumns(df)
    assert out["COTACAO 10Y PADRAO"].iloc[0] == [{"DATA": "01-01-2024", "PRECO": 10.0}]


def test_deserialize_jsoncolumns_handles_arrowdtype_binary():
    payload = zstd.ZstdCompressor(level=3).compress(b'[{"DATA": "01-01-2024", "PRECO": 10.5}]')
    df = pd.DataFrame(
        {"TICKER": ["PETR4"], "COTACAO 10Y PADRAO": pd.array([payload], dtype=pd.ArrowDtype(pa.binary()))}
    )

    out = deserializeJsonColumns(df)

    assert out["COTACAO 10Y PADRAO"].iloc[0] == [{"DATA": "01-01-2024", "PRECO": 10.5}]


def test_get_nest_keeps_compressed_column_subfields(monkeypatch, tmp_path):
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([df]))
    build_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    build_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.CACHE_FEATHER_PATH = build_mod.CACHE_FEATHER_PATH
    cache_mod.CACHE_NESTED_PATH = build_mod.CACHE_NESTED_PATH
    build_mod.buildFeatherCache()
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()

    rebuildAbbrevs()
    nest = getNest(m.STOCKS_CACHE, m.nestedSample)
    assert "COTACAO 10Y PADRAO" in nest
    assert set(nest["COTACAO 10Y PADRAO"]["subfields"]) >= {"DATA", "PRECO"}


def test_build_requests_presorted_rows(monkeypatch, tmp_path):
    seenSql = []

    def connect():
        conn = FakeConn([makeDf()])
        realExec = conn.exec_driver_sql

        def exec_driver_sql(sql):
            seenSql.append(sql)
            return realExec(sql)

        monkeypatch.setattr(conn, "exec_driver_sql", exec_driver_sql)
        return conn

    monkeypatch.setattr(build_mod.stocksEngine, "connect", connect)
    monkeypatch.setattr(build_mod, "CACHE_FEATHER_PATH", tmp_path / "cache.feather")
    monkeypatch.setattr(build_mod, "CACHE_NESTED_PATH", tmp_path / "nested.feather")

    build_mod.buildFeatherCache()

    assert any("ORDER BY TICKER ASC, TIME DESC" in sql for sql in seenSql)


def test_build_stamps_presorted_marker(monkeypatch, tmp_path):
    monkeypatch.setattr(build_mod.stocksEngine, "connect", lambda: FakeConn([makeDf()]))
    monkeypatch.setattr(build_mod, "CACHE_FEATHER_PATH", tmp_path / "cache.feather")
    monkeypatch.setattr(build_mod, "CACHE_NESTED_PATH", tmp_path / "nested.feather")

    build_mod.buildFeatherCache()

    table = feather.read_table(build_mod.CACHE_FEATHER_PATH)
    assert (table.schema.metadata or {}).get(PRESORTED_FLAG_KEY) == b"1"


def _writeFeather(rows, path):
    feather.write_feather(pd.DataFrame(rows), path)


def _loadManager(path, monkeypatch, tmp_path):
    manager = cache_mod.StocksCacheManager(MagicMock(), threading.Lock())
    monkeypatch.setattr(cache_mod, "CACHE_FEATHER_PATH", path)
    monkeypatch.setattr(cache_mod, "CACHE_NESTED_PATH", tmp_path / "nested.feather")
    return manager


def test_load_skips_sort_for_presorted_files(monkeypatch, tmp_path):
    path = tmp_path / "cache.feather"
    table = pa.Table.from_pandas(
        pd.DataFrame({"TICKER": ["VALE3", "PETR4"], "TIME": [pd.Timestamp("2024-01-01")] * 2}), preserve_index=False
    ).replace_schema_metadata({PRESORTED_FLAG_KEY: b"1"})
    with pa.OSFile(str(path), "wb") as sink, pa.ipc.new_file(sink, table.schema) as writer:
        writer.write_table(table)

    def boom(df):
        raise AssertionError("sort must not run for presorted files")

    monkeypatch.setattr(cache_mod, "sortCacheFrame", boom)
    manager = _loadManager(path, monkeypatch, tmp_path)

    manager.loadFromFeather()

    assert list(manager.STOCKS_CACHE["TICKER"]) == ["VALE3", "PETR4"]


def test_load_sorts_legacy_files_without_marker(monkeypatch, tmp_path):
    path = tmp_path / "cache.feather"
    _writeFeather(
        {"TICKER": ["VALE3", "PETR4"], "TIME": [pd.Timestamp("2024-01-01"), pd.Timestamp("2023-01-01")]}, path
    )
    manager = _loadManager(path, monkeypatch, tmp_path)

    manager.loadFromFeather()

    assert list(manager.STOCKS_CACHE["TICKER"]) == ["PETR4", "VALE3"]
