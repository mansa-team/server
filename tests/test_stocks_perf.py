import sys
import os
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
from main.app.stocks_api.cache import optimizeDtypes


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
