"""Unit tests for main/app/stocks_api/compress.py.

Covers the payload-compaction helpers used by the stocks MCP tools:
compactValue suffix/date logic, toColumnar, fixHeaders, compactRow,
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
    fixHeaders,
    getAbbr,
    getNest,
    rebuildAbbrevs,
    toColumnar,
    walk,
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

    def test_float_rounds_to_10_significant_digits(self):
        assert compactValue(3.14159265358979) == 3.141592654

    def test_int_trillion_suffix(self):
        assert compactValue(1_234_567_890_123) == "1.2T"

    def test_int_billion_suffix(self):
        assert compactValue(1_234_567_890) == "1.2B"

    def test_int_million_suffix_exact(self):
        assert compactValue(1_000_000) == "1M"

    def test_int_thousand_suffix(self):
        assert compactValue(2_500) == "2.5K"

    def test_int_below_thousand_unchanged(self):
        assert compactValue(999) == 999

    def test_negative_int_suffix(self):
        assert compactValue(-1_000_000) == "-1M"

    def test_bool_untouched(self):
        assert compactValue(True) is True
        assert compactValue(False) is False

    def test_df_date_compacts_to_mm_yy(self):
        assert compactValue("15-06-2026") == "06-15"

    def test_di_date_compacts_to_mm_dd(self):
        assert compactValue("2026-06-15") == "06-15"

    def test_non_matching_string_unchanged(self):
        assert compactValue("hello") == "hello"
        assert compactValue("15-06-202") == "15-06-202"


class TestWalk:
    """walk: recursive dict/list transform."""

    def test_recurses_dicts_and_lists(self):
        assert walk({"a": [1, {"b": 2}], "c": 3}, lambda v: v * 2) == {"a": [2, {"b": 4}], "c": 6}

    def test_scalar_leaf(self):
        assert walk("x", lambda v: v.upper()) == "X"


class TestToColumnar:
    """toColumnar: passthrough guards + happy-path columnar output."""

    def test_empty_list_unchanged(self):
        assert toColumnar([]) == []

    def test_single_row_unchanged(self):
        data = [{"a": 1}]
        assert toColumnar(data) == data

    def test_first_row_not_dict_unchanged(self):
        data = [[1, 2], [3, 4]]
        assert toColumnar(data) == data

    def test_mismatched_keys_unchanged(self):
        data = [{"a": 1}, {"b": 2}]
        assert toColumnar(data) == data

    def test_happy_path(self):
        data = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        assert toColumnar(data) == {"h": "a,b", "d": ["1|x", "2|y"]}


class TestFixHeaders:
    """fixHeaders: in-place COT remap of "h" headers."""

    def test_remaps_cot_headers(self):
        obj = {"h": "DATA,PRECO"}
        fixHeaders(obj)
        assert obj == {"h": "D,P"}

    def test_unknown_pieces_passthrough(self):
        obj = {"h": "DATA,FOO"}
        fixHeaders(obj)
        assert obj == {"h": "D,FOO"}

    def test_nested_dict_value(self):
        obj = {"inner": {"h": "PRECO"}}
        fixHeaders(obj)
        assert obj == {"inner": {"h": "P"}}

    def test_list_of_dicts_not_traversed(self):
        # edge case: fixHeaders only recurses into dict values whose values
        # are dicts; a list value is handed to fixHeaders, which is a no-op
        # because the top-level isinstance(obj, dict) guard fails.
        obj = {"rows": [{"h": "DATA"}]}
        fixHeaders(obj)
        assert obj == {"rows": [{"h": "DATA"}]}

    def test_non_str_h_value_untouched(self):
        obj = {"h": 5}
        fixHeaders(obj)
        assert obj == {"h": 5}


class TestCompactRow:
    """compactRow: meta/historical/fundamental abbreviation + nested handling."""

    def test_meta_keys_abbreviated(self):
        row = {"TICKER": "PETR4", "NOME": "PETROBRAS PN", "TIME": "2026-06-15"}
        assert compactRow(row, "get_fundamental", ABBR_STUB, {}) == {
            "TK": "PETR4",
            "NM": "PETROBRAS PN",
            "TI": "2026-06-15",
        }

    def test_historical_year_col(self):
        row = {"TICKER": "PETR4", "LUCRO LIQUIDO 2024": 50000}
        assert compactRow(row, "get_historical", ABBR_STUB, {}) == {"TK": "PETR4", "LL.24": 50000}

    def test_historical_fallback_first_letters(self):
        row = {"RECEITA LIQUIDA 2023": 100000}
        assert compactRow(row, "get_historical", ABBR_STUB, {}) == {"RL.23": 100000}

    def test_historical_space_key_without_year_passthrough(self):
        row = {"LUCRO LIQUIDO": 1}
        assert compactRow(row, "get_historical", ABBR_STUB, {}) == {"LUCRO LIQUIDO": 1}

    def test_fundamental_keys_abbreviated(self):
        row = {"P/L": 5.2}
        assert compactRow(row, "get_fundamental", ABBR_STUB, {}) == {"PL": 5.2}

    def test_unknown_key_passthrough(self):
        row = {"FOO": 1, "P/L": 2}
        assert compactRow(row, "get_fundamental", ABBR_STUB, {}) == {"FOO": 1, "PL": 2}

    def test_nested_rename_drop_cap(self):
        row = {
            "NOTICIAS": [
                {"TITULO": "a", "LINK": "http://x", "EXTRA": "e"},
                {"TITULO": "b", "LINK": "http://y"},
                {"TITULO": "c", "LINK": "http://z"},
            ]
        }
        assert compactRow(row, "get_fundamental", ABBR_STUB, NEST_STUB) == {
            "NOTICIAS": [{"T": "a", "EXTRA": "e"}, {"T": "b"}]
        }

    def test_nested_defaults_when_spec_omits_options(self):
        nests = {"NOTICIAS": {"subfields": {"TITULO": "T"}}}
        row = {"NOTICIAS": [{"TITULO": "a", "LINK": "x"}]}
        assert compactRow(row, "get_fundamental", ABBR_STUB, nests) == {"NOTICIAS": [{"T": "a", "LINK": "x"}]}

    def test_nested_field_not_list_untouched(self):
        row = {"NOTICIAS": "x"}
        assert compactRow(row, "get_fundamental", ABBR_STUB, NEST_STUB) == {"NOTICIAS": "x"}

    def test_nested_non_dict_items_kept(self):
        row = {"NOTICIAS": [1, 2]}
        assert compactRow(row, "get_fundamental", ABBR_STUB, NEST_STUB) == {"NOTICIAS": [1, 2]}


class TestCompactCotations:
    """compactCotations: single/multi entry compaction + passthroughs."""

    def test_non_list_data_unchanged(self):
        result = {"data": "x", "count": 1}
        assert compactCotations(result) == {"data": "x", "count": 1}

    def test_missing_data_unchanged(self):
        result = {"count": 1}
        assert compactCotations(result) == {"count": 1}

    def test_single_entry(self):
        result = {
            "data": [
                {
                    "TICKER": "PETR4",
                    "NOME": "PETROBRAS PN",
                    "TIME": "2026-06-15",
                    "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 28.5}],
                }
            ]
        }
        out = compactCotations(result)
        assert out == {
            "TK": "PETR4",
            "NM": "PETROBRAS PN",
            "TI": "06-15",
            "C10": {"h": "D,P", "d": ["06-15|28.5"]},
        }
        assert "data" not in out

    def test_single_entry_non_10y_key_name(self):
        result = {"data": [{"TICKER": "PETR4", "COTACAO PADRAO": [{"DATA": "15-06-2026", "PRECO": 1.0}]}]}
        out = compactCotations(result)
        assert out == {
            "TK": "PETR4",
            "NM": "",
            "TI": "",
            "COTA": {"h": "D,P", "d": ["06-15|1.0"]},
        }

    def test_single_entry_missing_nome_time_default_empty(self):
        result = {"data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": [{"DATA": "15-06-2026", "PRECO": 1.0}]}]}
        out = compactCotations(result)
        assert out == {"TK": "PETR4", "NM": "", "TI": "", "C10": {"h": "D,P", "d": ["06-15|1.0"]}}

    def test_single_entry_no_cotation_key_unchanged(self):
        result = {"data": [{"TICKER": "PETR4"}]}
        assert compactCotations(result) == result

    def test_single_entry_empty_cotation_list_unchanged(self):
        result = {"data": [{"TICKER": "PETR4", "COTACAO 10Y PADRAO": []}]}
        assert compactCotations(result) == result

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

    def test_pops_metadata_present_in_args(self):
        raw = {
            "count": 2,
            "search": "PETR4",
            "fields": ["P/L"],
            "dates": "2024",
            "type": "get_fundamental",
            "data": [],
        }
        out = compressResponse(raw, "get_fundamental", {"search": "PETR4", "fields": ["P/L"], "dates": "2024"})
        assert out == {"data": []}

    def test_keeps_metadata_not_in_args(self):
        raw = {"count": 1, "search": "PETR4", "type": "get_fundamental", "data": []}
        assert compressResponse(raw, "get_fundamental", {}) == {"search": "PETR4", "data": []}

    def test_empty_data_list_passthrough(self):
        raw = {"count": 0, "type": "get_fundamental", "data": []}
        assert compressResponse(raw, "get_fundamental", {}) == {"data": []}

    def test_data_not_list_passthrough(self):
        raw = {"type": "get_fundamental", "data": {"foo": 1}}
        assert compressResponse(raw, "get_fundamental", {}) == {"data": {"foo": 1}}

    def test_data_non_dict_entries_passthrough(self):
        raw = {"data": [1, 2]}
        assert compressResponse(raw, "get_fundamental", {}) == {"data": [1, 2]}

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

    def test_get_cotations_data_not_list(self):
        raw = {"type": "get_cotations", "data": "x"}
        assert compressResponse(raw, "get_cotations", {}) == {"data": "x"}

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

    def test_get_live_price_data_not_list(self):
        raw = {"type": "get_live_price", "data": {"TICKER": "PETR4"}}
        assert compressResponse(raw, "get_live_price", {}) == {"data": {"TICKER": "PETR4"}}

    def test_multi_row_columnar_with_fallback_abbrs(self):
        # cache absent: fallback abbrs have empty historical/fundamental,
        # so "P/L" passes through unabbreviated.
        raw = {
            "count": 2,
            "type": "get_fundamental",
            "data": [
                {"TICKER": "PETR4", "P/L": 5.2},
                {"TICKER": "VALE3", "P/L": 6.5},
            ],
        }
        out = compressResponse(raw, "get_fundamental", {})
        assert out == {"data": {"h": "TK,P/L", "d": ["PETR4|5.2", "VALE3|6.5"]}}

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
        # note: walk(compactValue) suffixes int leaves, so year values become "50K"/"100K";
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
