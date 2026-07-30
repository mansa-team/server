import sys
import os
import json
import tempfile
import shutil
from datetime import date
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.stocks_api.query import filterCotationColumn
from main.app.stocks_api.cache import buildCotationDateIndex, optimizeDtypes


# ── buildCotationDateIndex ──────────────────────────────────────────────


def test_build_date_index_basic():
    data = [
        [{"DATA": "15-01-2024", "PRECO": 28.5}, {"DATA": "20-12-2024", "PRECO": 30.0}],
        [{"DATA": "01-06-2024", "PRECO": 25.0}],
    ]
    df = pd.DataFrame({"COTACAO 10Y PADRAO": [json.dumps(d) for d in data]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx[0] == ("15-01-2024", "20-12-2024")
    assert idx[1] == ("01-06-2024", "01-06-2024")


def test_build_date_index_missing_column():
    df = pd.DataFrame({"OTHER": ["[]"]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx == {}


def test_build_date_index_empty_column():
    df = pd.DataFrame({"COTACAO 10Y PADRAO": [None, np.nan]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx == {}


def test_build_date_index_malformed_json():
    df = pd.DataFrame({"COTACAO 10Y PADRAO": ["not json", "also {bad"]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx == {}


def test_build_date_index_non_list_json():
    df = pd.DataFrame({"COTACAO 10Y PADRAO": ['{"key": "value"}']})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx == {}


def test_build_date_index_empty_entries():
    df = pd.DataFrame({"COTACAO 10Y PADRAO": [json.dumps([])]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx == {}


def test_build_date_index_entry_without_data_key():
    entries = [{"PRECO": 10.0}, {"DATA": "15-01-2024", "PRECO": 20.0}]
    df = pd.DataFrame({"COTACAO 10Y PADRAO": [json.dumps(entries)]})
    idx = buildCotationDateIndex(df, "COTACAO 10Y PADRAO")
    assert idx[0] == ("15-01-2024", "15-01-2024")


# ── filterCotationColumn without date index ─────────────────────────────


def test_filter_no_dates_returns_original():
    data = [[{"DATA": "15-01-2024", "PRECO": 28.5}]]
    series = pd.Series(data)
    result = filterCotationColumn(series, None, None)
    assert result.tolist() == data


def test_filter_no_start_date_returns_original():
    data = [[{"DATA": "15-01-2024", "PRECO": 28.5}]]
    series = pd.Series(data)
    result = filterCotationColumn(series, None, date(2024, 12, 31))
    assert result.tolist() == data


def test_filter_basic_no_index():
    data = [
        [{"DATA": "15-01-2024", "PRECO": 28.5}, {"DATA": "16-01-2024", "PRECO": 29.0}],
        [{"DATA": "20-01-2024", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    result = filterCotationColumn(series, date(2024, 1, 15), date(2024, 1, 15))
    assert len(result[0]) == 1
    assert result[0][0]["PRECO"] == 28.5
    assert len(result[1]) == 0


def test_filter_empty_series_no_index():
    series = pd.Series([[], []])
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31))
    assert all(r == [] for r in result)


def test_filter_all_out_of_range_no_index():
    data = [
        [{"DATA": "15-01-2020", "PRECO": 10.0}],
        [{"DATA": "20-12-2025", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31))
    assert all(len(r) == 0 for r in result)


def test_filter_full_range_no_index():
    data = [
        [{"DATA": "15-01-2024", "PRECO": 28.5}, {"DATA": "01-06-2024", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31))
    assert len(result[0]) == 2


# ── filterCotationColumn with date index ────────────────────────────────


def test_filter_with_date_index_skips_out_of_range():
    data = [
        [{"DATA": "15-01-2020", "PRECO": 10.0}],
        [{"DATA": "15-01-2024", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    dateIndex = {0: ("15-01-2020", "15-01-2020"), 1: ("15-01-2024", "15-01-2024")}
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31), dateIndex=dateIndex)
    assert len(result[0]) == 0
    assert len(result[1]) == 1


def test_filter_with_date_index_all_candidates():
    data = [
        [{"DATA": "15-01-2024", "PRECO": 28.5}],
        [{"DATA": "01-06-2024", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    dateIndex = {0: ("15-01-2024", "15-01-2024"), 1: ("01-06-2024", "01-06-2024")}
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31), dateIndex=dateIndex)
    assert len(result[0]) == 1
    assert len(result[1]) == 1


def test_filter_with_date_index_no_candidates():
    data = [
        [{"DATA": "15-01-2020", "PRECO": 10.0}],
        [{"DATA": "20-12-2025", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    dateIndex = {0: ("15-01-2020", "15-01-2020"), 1: ("20-12-2025", "20-12-2025")}
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31), dateIndex=dateIndex)
    assert all(len(r) == 0 for r in result)


def test_filter_with_date_index_partial_overlap():
    data = [
        [{"DATA": "01-12-2023", "PRECO": 10.0}, {"DATA": "15-01-2024", "PRECO": 28.5}],
        [{"DATA": "15-06-2024", "PRECO": 30.0}],
    ]
    series = pd.Series(data)
    dateIndex = {0: ("01-12-2023", "15-01-2024"), 1: ("15-06-2024", "15-06-2024")}
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31), dateIndex=dateIndex)
    assert len(result[0]) == 1
    assert result[0][0]["PRECO"] == 28.5
    assert len(result[1]) == 1


def test_filter_with_date_index_empty_index():
    data = [[{"DATA": "15-01-2024", "PRECO": 28.5}]]
    series = pd.Series(data)
    result = filterCotationColumn(series, date(2024, 1, 1), date(2024, 12, 31), dateIndex={})
    assert len(result[0]) == 1
    assert result[0][0]["PRECO"] == 28.5


# ── optimizeDtypes ──────────────────────────────────────────────────────


def test_optimize_dtypes_categories():
    df = pd.DataFrame({"TICKER": ["PETR4", "VALE3"], "NOME": ["Petrobras", "Vale"]})
    result = optimizeDtypes(df)
    assert result["TICKER"].dtype.name == "category"
    assert result["NOME"].dtype.name == "category"


def test_optimize_dtypes_float_downcast():
    df = pd.DataFrame({"PRECO": [1.0, 2.0, 3.0]})
    result = optimizeDtypes(df)
    assert result["PRECO"].dtype == np.float32


def test_optimize_dtypes_string_pyarrow():
    df = pd.DataFrame({"TICKER": ["A"], "COL": ["hello"]})
    result = optimizeDtypes(df)
    assert "string" in str(result["COL"].dtype).lower() or result["COL"].dtype == object


def test_optimize_dtypes_preserves_data():
    df = pd.DataFrame({"TICKER": ["PETR4"], "NOME": ["Petrobras"], "PRECO": [28.5]})
    result = optimizeDtypes(df)
    assert result["TICKER"].iloc[0] == "PETR4"
    assert result["NOME"].iloc[0] == "Petrobras"


# ── Parquet cache ───────────────────────────────────────────────────────


def test_parquet_cache_file_created(tmp_path):
    parquet_path = tmp_path / "stocks_cache.parquet"
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["Petrobras"],
            "PRECO": [28.5],
        }
    )
    df.to_parquet(parquet_path, index=False)
    loaded = pd.read_parquet(parquet_path)
    assert len(loaded) == 1
    assert loaded["TICKER"].iloc[0] == "PETR4"


def test_parquet_cache_roundtrip_dtypes(tmp_path):
    parquet_path = tmp_path / "stocks_cache.parquet"
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "NOME": ["Petrobras", "Vale"],
            "PRECO": [28.5, 65.0],
        }
    )
    df.to_parquet(parquet_path, index=False)
    loaded = pd.read_parquet(parquet_path)
    assert list(loaded.columns) == list(df.columns)
    assert loaded["PRECO"].dtype in [np.float64, np.float32]


def test_parquet_cache_json_column(tmp_path):
    parquet_path = tmp_path / "stocks_cache.parquet"
    cotation = json.dumps([{"DATA": "15-01-2024", "PRECO": 28.5}])
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "COTACAO 10Y PADRAO": [cotation],
        }
    )
    df.to_parquet(parquet_path, index=False)
    loaded = pd.read_parquet(parquet_path)
    parsed = json.loads(loaded["COTACAO 10Y PADRAO"].iloc[0])
    assert parsed[0]["DATA"] == "15-01-2024"
