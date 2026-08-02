import threading
import zstandard as zstd

import pandas as pd

from main.app.stocks_api.cache import StocksCacheManager, COMPRESS_COLS
from main.app.stocks_api.query import StocksQueryManager, filterCotationColumn


def test_filter_cotation_column_does_not_accept_date_index():
    series = pd.Series([[{"DATA": "01-01-2024", "PRECO": 10.0}, {"DATA": "15-06-2026", "PRECO": 11.0}]])
    try:
        filterCotationColumn(
            series, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"), {"0": ("01-01-2020", "01-01-2027")}
        )
    except TypeError:
        pass
    else:
        raise AssertionError("dateIndex parameter should have been removed")


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
    import main.app.stocks_api.cache as cache_mod

    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([df]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()
    assert not hasattr(m, "cotationDateIndex")


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


def test_get_cached_stocks_compresses_json_columns(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([makeDf()]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    monkeypatch.setattr(cache_mod.subprocess, "run", lambda *a, **k: None)
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()
    df = m.STOCKS_CACHE
    assert isinstance(df["COTACAO 10Y PADRAO"].iloc[0], bytes)
    assert zstd.ZstdDecompressor().decompress(df["COTACAO 10Y PADRAO"].iloc[0]).decode("utf-8").startswith("[{")
    assert isinstance(df["NOTICIAS"].iloc[0], bytes)
    assert df["NOTICIAS"].iloc[1] is None  # NaN/None cells stay None


def test_get_cached_stocks_keeps_raw_nested_sample(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([makeDf()]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert nested["COTACAO 10Y PADRAO"].iloc[0].startswith("[{")


def test_nested_sample_skips_all_null_leading_rows(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    empty = pd.DataFrame(
        {
            "TICKER": ["AAA1", "BBB2"],
            "NOME": ["x", "y"],
            "COTACAO 10Y PADRAO": [None, None],
            "NOTICIAS": [None, None],
        }
    )
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([empty, makeDf()]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert nested["COTACAO 10Y PADRAO"].iloc[0].startswith("[{")


def test_nested_sample_captures_sparse_columns_across_chunks(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

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
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([first, later]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    nested = pd.read_feather(cache_mod.CACHE_NESTED_PATH)
    assert nested is not None
    assert isinstance(nested["COTACAO 10Y PADRAO"].iloc[0], str)
    assert isinstance(nested["NOTICIAS"].iloc[0], str)
    assert nested["NOTICIAS"].iloc[0].startswith("[{")


def test_detect_nested_fields_tolerates_loose_nan_json():
    from main.app.stocks_api.util import detectNestedFields

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
    from main.app.stocks_api.util import detectNestedFields

    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOTICIAS": ["[]", '[{"TITULO": "a", "LINK": "http://x"}]'],
        }
    )
    nest = detectNestedFields(df)
    assert "NOTICIAS" in nest
    assert set(nest["NOTICIAS"]["subfields"]) >= {"TITULO", "LINK"}


def test_deserialize_json_columns_decompresses_bytes():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "COTACAO 10Y PADRAO": [zstd.ZstdCompressor(level=3).compress(b'[{"DATA": "01-01-2024", "PRECO": 10.0}]')],
        }
    )
    manager = StocksQueryManager(type("Fake", (), {"STOCKS_CACHE": None, "tickerIndex": {}, "nestedSample": None})())
    out = manager.deserializeJsonColumns(df)
    assert out["COTACAO 10Y PADRAO"].iloc[0] == [{"DATA": "01-01-2024", "PRECO": 10.0}]


def test_get_nest_keeps_compressed_column_subfields(monkeypatch, tmp_path):
    import main.app.stocks_api.cache as cache_mod

    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: iter([df]))
    cache_mod.CACHE_FEATHER_PATH = tmp_path / "cache.feather"
    cache_mod.CACHE_NESTED_PATH = tmp_path / "nested.feather"
    cache_mod.buildFeatherCache()
    m = StocksCacheManager(None, threading.Lock())
    m.getCachedStocks()
    from unittest.mock import patch
    from main.app.stocks_api.cache import stocksCache
    from main.app.stocks_api.compress import getNest, rebuildAbbrevs

    with (
        patch.object(stocksCache, "STOCKS_CACHE", m.STOCKS_CACHE),
        patch.object(stocksCache, "nestedSample", m.nestedSample),
    ):
        rebuildAbbrevs()
        nest = getNest()
    assert "COTACAO 10Y PADRAO" in nest
    assert set(nest["COTACAO 10Y PADRAO"]["subfields"]) >= {"DATA", "PRECO"}
