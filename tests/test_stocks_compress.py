"""Unit tests for main/app/stocks_api/compress.py.

Covers the payload-compaction helpers used by the stocks MCP tools:
compactValue suffix/date logic, compactRow,
compactCotations, the compressResponse pipeline, and the lazy
abbr/nest caches (getAbbr/getNest/rebuildAbbrevs).

Pure unit tests: no MySQL required. Cache-dependent functions are
exercised by patching stocksCache attributes; the module-level
abbr/nest globals are reset before and after every test so the
suite is order-independent.
"""

from unittest.mock import patch

import pandas as pd
import pytest

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.compress import (
    compactCotations,
    compactRow,
    compactValue,
    compressResponse,
    getAbbr,
    getNest,
    rebuildAbbrevs,
)

# Stub abbreviation/nesting tables for direct compactRow tests.
ABBR_STUB = {
    "meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"},
    "historical": {"LUCRO LIQUIDO": "LL"},
    "fundamental": {"P/L": "PL"},
}

NEST_STUB = {
    "NOTICIAS": {
        "subfields": {"TITULO": "T", "LINK": "L"},
        "dropped_in_compact": ["LINK"],
        "max_items_compact": 2,
    }
}

ABBR_FALLBACK = {
    "meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"},
    "historical": {},
    "fundamental": {},
}


@pytest.fixture(autouse=True)
def reset_abbrev_globals():
    """compress.py caches abbr/nest in module globals; reset before and after each test."""
    rebuildAbbrevs()
    yield
    rebuildAbbrevs()


class TestCompactValue:
    """compactValue: float rounding, int suffixes, date compaction, passthroughs."""

    @pytest.mark.parametrize(
        "value,expected",
        [
            (3.14159265358979, 3.141592654),
            (1_234_567_890_123, "1.2T"),
            (1_234_567_890, "1.2B"),
            (1_000_000, "1M"),
            (2_500, "2.5K"),
            (999, 999),
            (-1_000_000, "-1M"),
            ("15-06-2026", "06-15"),
            ("2026-06-15", "06-15"),
            ("hello", "hello"),
            ("15-06-202", "15-06-202"),
        ],
    )
    def test_value_cases(self, value, expected):
        assert compactValue(value) == expected

    def test_bool_untouched(self):
        assert compactValue(True) is True
        assert compactValue(False) is False


class TestCompactRow:
    """compactRow: meta/historical/fundamental abbreviation + nested handling."""

    @pytest.mark.parametrize(
        "row,tool,nests,expected",
        [
            (
                {"TICKER": "PETR4", "NOME": "PETROBRAS PN", "TIME": "2026-06-15"},
                "get_fundamental",
                {},
                {"TK": "PETR4", "NM": "PETROBRAS PN", "TI": "2026-06-15"},
            ),
            (
                {"TICKER": "PETR4", "LUCRO LIQUIDO 2024": 50000},
                "get_historical",
                {},
                {"TK": "PETR4", "LL.24": 50000},
            ),
            (
                {"RECEITA LIQUIDA 2023": 100000},
                "get_historical",
                {},
                {"RL.23": 100000},
            ),
            (
                {"LUCRO LIQUIDO": 1},
                "get_historical",
                {},
                {"LUCRO LIQUIDO": 1},
            ),
            ({"P/L": 5.2}, "get_fundamental", {}, {"PL": 5.2}),
            ({"FOO": 1, "P/L": 2}, "get_fundamental", {}, {"FOO": 1, "PL": 2}),
            (
                {
                    "NOTICIAS": [
                        {"TITULO": "a", "LINK": "http://x", "EXTRA": "e"},
                        {"TITULO": "b", "LINK": "http://y"},
                        {"TITULO": "c", "LINK": "http://z"},
                    ]
                },
                "get_fundamental",
                NEST_STUB,
                {"NOTICIAS": [{"T": "a", "EXTRA": "e"}, {"T": "b"}]},
            ),
            (
                {"NOTICIAS": [{"TITULO": "a", "LINK": "x"}]},
                "get_fundamental",
                {"NOTICIAS": {"subfields": {"TITULO": "T"}}},
                {"NOTICIAS": [{"T": "a", "LINK": "x"}]},
            ),
            ({"NOTICIAS": "x"}, "get_fundamental", NEST_STUB, {"NOTICIAS": "x"}),
            ({"NOTICIAS": [1, 2]}, "get_fundamental", NEST_STUB, {"NOTICIAS": [1, 2]}),
        ],
    )
    def test_row_cases(self, row, tool, nests, expected):
        assert compactRow(row, tool, ABBR_STUB, nests) == expected


class TestCompactCotations:
    """compactCotations: single/multi entry compaction + passthroughs."""

    @pytest.mark.parametrize(
        "result",
        [
            {"data": "x", "count": 1},
            {"count": 1},
            {"data": [{"TICKER": "PETR4"}]},
            {"data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": []}]},
            {"data": [1, 2]},
        ],
    )
    def test_passthrough_unchanged(self, result):
        assert compactCotations(result) == result

    @pytest.mark.parametrize(
        "entry,expected",
        [
            (
                {
                    "TICKER": "PETR4",
                    "NOME": "PETROBRAS PN",
                    "TIME": "2026-06-15",
                    "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 28.5}],
                },
                {
                    "TK": "PETR4",
                    "NM": "PETROBRAS PN",
                    "TI": "06-15",
                    "C10": {"h": "D,P", "d": ["06-15|28.5"]},
                },
            ),
            (
                {"TICKER": "PETR4", "COTACAO PADRAO": [{"DATA": "15-06-2026", "PRECO": 1.0}]},
                {"TK": "PETR4", "NM": "", "TI": "", "COTA": {"h": "D,P", "d": ["06-15|1.0"]}},
            ),
            (
                {"TICKER": "PETR4", "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 1.0}]},
                {"TK": "PETR4", "NM": "", "TI": "", "C10": {"h": "D,P", "d": ["06-15|1.0"]}},
            ),
        ],
    )
    def test_single_entry_compaction(self, entry, expected):
        out = compactCotations({"data": [entry]})
        assert out == expected
        assert "data" not in out

    def test_multi_entry(self):
        result = {
            "data": [
                {"TICKER": "PETR4", "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 1.0}]},
                {"TICKER": "VALE3", "COTACAO 10Y PADRAO": [{"DATA": "16-06-2026", "PRECO": 2.0}]},
            ]
        }
        out = compactCotations(result)
        assert out["data"][0] == {
            "TICKER": "PETR4",
            "COTACAO 10Y PADRAO": {"h": "D,P", "d": ["06-15|1.0"]},
        }
        assert out["data"][1] == {
            "TICKER": "VALE3",
            "COTACAO 10Y PADRAO": {"h": "D,P", "d": ["06-16|2.0"]},
        }

    def test_multi_entry_non_dict_entries_unchanged(self):
        result = {"data": [1, 2]}
        assert compactCotations(result) == result

    def test_to_col_non_dict_rows(self):
        result = {"data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": [["a", "b"], ["c", "d"]]}]}
        out = compactCotations(result)
        assert out["C10"] == {"h": "v", "d": ["a|b", "c|d"]}


class TestAbbrevCaches:
    """getAbbr/getNest/rebuildAbbrevs: fallbacks, cache-present discovery, resets."""

    def test_get_abbr_cache_absent_fallback(self):
        with patch.object(stocksCache, "STOCKS_CACHE", None):
            rebuildAbbrevs()
            assert getAbbr() == ABBR_FALLBACK

    def test_get_nest_cache_absent_fallback(self):
        with patch.object(stocksCache, "STOCKS_CACHE", None):
            rebuildAbbrevs()
            assert getNest() == {}

    def test_get_abbr_cache_present(self):
        df = pd.DataFrame(
            {
                "TICKER": ["PETR4"],
                "NOME": ["PETROBRAS PN"],
                "TIME": ["2026-06-15"],
                "LUCRO LIQUIDO 2024": [50000],
                "P/L": [5.2],
            }
        )
        with patch.object(stocksCache, "STOCKS_CACHE", df):
            rebuildAbbrevs()
            abbr = getAbbr()
        assert abbr["meta"] == {"TICKER": "TK", "NOME": "NM", "TIME": "TI"}
        assert abbr["historical"] == {"LUCRO LIQUIDO": "LL"}
        assert abbr["fundamental"] == {"P/L": "PL"}

    def test_get_nest_cache_present_merges_nested_sample(self):
        df = pd.DataFrame({"TICKER": ["PETR4"], "NOTICIAS": ['[{"TITULO": "a", "LINK": "http://x"}]']})
        nested = pd.DataFrame(
            {
                "NOTICIAS": ['[{"TITULO": "a", "LINK": "http://x"}]'],
                "DIVIDENDOS": ['[{"DATA": "01-01-2024"}]'],
            }
        )
        with (
            patch.object(stocksCache, "STOCKS_CACHE", df),
            patch.object(stocksCache, "nestedSample", nested),
        ):
            rebuildAbbrevs()
            nest = getNest()
        assert set(nest["NOTICIAS"]["subfields"]) >= {"TITULO", "LINK"}
        assert nest["NOTICIAS"]["dropped_in_compact"] == ["LINK"]
        assert nest["NOTICIAS"]["max_items_compact"] == 5
        # nestedSample-only column merged in via setdefault
        assert "DIVIDENDOS" in nest

    def test_get_abbr_cached_across_calls(self):
        df = pd.DataFrame({"TICKER": ["X"]})
        with patch.object(stocksCache, "STOCKS_CACHE", df):
            rebuildAbbrevs()
            assert getAbbr() is getAbbr()

    def test_rebuild_abbrevs_resets_globals(self):
        df = pd.DataFrame({"TICKER": ["PETR4"], "LUCRO LIQUIDO 2024": [1]})
        with patch.object(stocksCache, "STOCKS_CACHE", df):
            rebuildAbbrevs()
            assert getAbbr()["historical"] != {}
        rebuildAbbrevs()
        with patch.object(stocksCache, "STOCKS_CACHE", None):
            assert getAbbr() == ABBR_FALLBACK
            assert getNest() == {}


class TestCompressResponse:
    """compressResponse: pipeline orchestration across tools."""

    @pytest.mark.parametrize(
        "raw,tool,args,expected",
        [
            (
                {
                    "count": 2,
                    "search": "PETR4",
                    "fields": ["P/L"],
                    "dates": "2024",
                    "type": "get_fundamental",
                    "data": [],
                },
                "get_fundamental",
                {"search": "PETR4", "fields": ["P/L"], "dates": "2024"},
                {"data": []},
            ),
            (
                {"count": 1, "search": "PETR4", "type": "get_fundamental", "data": []},
                "get_fundamental",
                {},
                {"search": "PETR4", "data": []},
            ),
            (
                {"count": 0, "type": "get_fundamental", "data": []},
                "get_fundamental",
                {},
                {"data": []},
            ),
            (
                {"type": "get_fundamental", "data": {"foo": 1}},
                "get_fundamental",
                {},
                {"data": {"foo": 1}},
            ),
            (
                {"data": [1, 2]},
                "get_fundamental",
                {},
                {"data": [1, 2]},
            ),
            (
                {"type": "get_cotations", "data": "x"},
                "get_cotations",
                {},
                {"data": "x"},
            ),
            (
                {"type": "get_live_price", "data": {"TICKER": "PETR4"}},
                "get_live_price",
                {},
                {"data": {"TICKER": "PETR4"}},
            ),
        ],
    )
    def test_passthrough_cases(self, raw, tool, args, expected):
        assert compressResponse(raw, tool, args) == expected

    def test_get_cotations_branch(self):
        raw = {
            "count": 1,
            "search": "PETR4",
            "type": "get_cotations",
            "data": [
                {
                    "TICKER": "PETR4",
                    "NOME": "PETROBRAS PN",
                    "TIME": "2026-06-15",
                    "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 28.5}],
                }
            ],
        }
        out = compressResponse(raw, "get_cotations", {"search": "PETR4"})
        assert out == {
            "TK": "PETR4",
            "NM": "PETROBRAS PN",
            "TI": "06-15",
            "C10": {"h": "D,P", "d": ["06-15|28.5"]},
        }

    def test_get_live_price_remaps_price_keys(self):
        raw = {
            "count": 1,
            "search": "PETR4",
            "type": "get_live_price",
            "data": [
                {
                    "TICKER": "PETR4",
                    "PRECO ATUAL": 28.5,
                    "PRECO ORIGINAL": 28.3,
                    "PRECO MINIMO": 28.0,
                    "PRECO MAXIMO": 28.8,
                    "PRECO MEDIO": 28.45,
                }
            ],
        }
        out = compressResponse(raw, "get_live_price", {"search": "PETR4"})
        # the single row is unwrapped from a list but stays under the "data" key
        assert out == {
            "data": {
                "TK": "PETR4",
                "PA": 28.5,
                "PO": 28.3,
                "PMN": 28.0,
                "PMX": 28.8,
                "PMD": 28.45,
            }
        }

    def test_multi_row_list_of_dicts_with_fallback_abbrs(self):
        # cache absent: fallback abbrs have empty historical/fundamental,
        # so "P/L" passes through unabbreviated. Multi-row results stay
        # as a list of dicts (generic h/d pipe-encoding removed; only
        # the nested cotation path uses h/d).
        raw = {
            "count": 2,
            "type": "get_fundamental",
            "data": [
                {"TICKER": "PETR4", "P/L": 5.2},
                {"TICKER": "VALE3", "P/L": 6.5},
            ],
        }
        out = compressResponse(raw, "get_fundamental", {})
        assert out == {"data": [{"TK": "PETR4", "P/L": 5.2}, {"TK": "VALE3", "P/L": 6.5}]}

    def test_single_row_unwrapped_with_cache_abbrevs(self):
        df = pd.DataFrame({"TICKER": ["PETR4"], "P/L": [5.2]})
        raw = {"data": [{"TICKER": "PETR4", "P/L": 5.2}]}
        with patch.object(stocksCache, "STOCKS_CACHE", df):
            rebuildAbbrevs()
            out = compressResponse(raw, "get_fundamental", {})
        assert out == {"data": {"TK": "PETR4", "PL": 5.2}}

    def test_get_historical_year_cols_with_cache_abbrevs(self):
        df = pd.DataFrame(
            {
                "TICKER": ["PETR4"],
                "NOME": ["PETROBRAS PN"],
                "TIME": ["2026-06-15"],
                "LUCRO LIQUIDO 2024": [50000],
                "RECEITA LIQUIDA 2023": [100000],
            }
        )
        raw = {
            "count": 1,
            "search": "PETR4",
            "type": "get_historical",
            "dates": "2023,2024",
            "data": [
                {
                    "TICKER": "PETR4",
                    "NOME": "PETROBRAS PN",
                    "TIME": "2026-06-15",
                    "LUCRO LIQUIDO 2024": 50000,
                    "RECEITA LIQUIDA 2023": 100000,
                }
            ],
        }
        with patch.object(stocksCache, "STOCKS_CACHE", df):
            rebuildAbbrevs()
            out = compressResponse(raw, "get_historical", {"search": "PETR4", "dates": "2023,2024"})
        # note: leaf compaction suffixes int leaves, so year values become "50K"/"100K";
        # the single row is unwrapped from a list but stays under the "data" key
        assert out == {
            "data": {
                "TK": "PETR4",
                "NM": "PETROBRAS PN",
                "TI": "06-15",
                "LL.24": "50K",
                "RL.23": "100K",
            }
        }
