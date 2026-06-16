"""Tests for main/app/stocks_api/util.py — covers normalizeColumns and edge cases."""

import pandas as pd
import pytest
from fastapi import HTTPException
from main.app.stocks_api.util import categorizeColumns, parseDateRange, normalizeColumns


class TestCategorizeColumns:
    def test_historical_and_fundamental(self):
        cols = ["PRECO ABERTO 2022", "PRECO ABERTO 2023", "VOLUME 2022", "P/L", "TICKER", "NOME", "TIME"]
        hist, fund = categorizeColumns(cols)
        assert "PRECO ABERTO" in hist
        assert sorted(hist["PRECO ABERTO"]) == [2022, 2023]
        assert "VOLUME" in hist
        assert hist["VOLUME"] == [2022]
        assert fund == ["P/L"]

    def test_only_fundamental(self):
        cols = ["P/L", "P/VP", "DIVIDEND_YIELD"]
        hist, fund = categorizeColumns(cols)
        assert hist == {}
        assert fund == ["P/L", "P/VP", "DIVIDEND_YIELD"]

    def test_reserved_words_excluded(self):
        cols = ["TICKER", "NOME", "TIME"]
        hist, fund = categorizeColumns(cols)
        assert hist == {}
        assert fund == []

    def test_single_year(self):
        cols = ["FECHAMENTO 2024"]
        hist, fund = categorizeColumns(cols)
        assert hist["FECHAMENTO"] == [2024]

    def test_no_year_suffix(self):
        cols = ["VOLUME"]
        hist, fund = categorizeColumns(cols)
        assert hist == {}
        assert fund == ["VOLUME"]


class TestParseDateRange:
    def test_empty_string(self):
        assert parseDateRange("") == (None, None)

    def test_none(self):
        assert parseDateRange(None) == (None, None)

    def test_single_year(self):
        start, end = parseDateRange("2023")
        assert start.year == 2023
        assert start.month == 1
        assert start.day == 1
        assert end.year == 2023
        assert end.month == 12
        assert end.day == 31

    def test_year_range(self):
        start, end = parseDateRange("2022,2024")
        assert start.year == 2022
        assert end.year == 2024

    def test_spaces(self):
        start, end = parseDateRange(" 2022 , 2024 ")
        assert start.year == 2022
        assert end.year == 2024

    def test_three_values_raises(self):
        with pytest.raises(HTTPException) as exc_info:
            parseDateRange("2022,2023,2024")
        assert exc_info.value.status_code == 400

    def test_month_start(self):
        start, end = parseDateRange("2026-06")
        assert start.month == 6
        assert start.day == 1
        assert end.month == 6
        assert end.day == 30

    def test_full_date(self):
        start, end = parseDateRange("2026-06-15")
        assert start == end


class TestNormalizeColumns:
    def test_reorder_columns(self):
        df = pd.DataFrame({"C": [1], "A": [2], "B": [3]})
        result = normalizeColumns(df, ["A", "B", "C"])
        assert list(result.columns) == ["A", "B", "C"]

    def test_partial_order(self):
        df = pd.DataFrame({"C": [1], "A": [2], "B": [3]})
        result = normalizeColumns(df, ["B"])
        assert list(result.columns) == ["B", "A", "C"]

    def test_missing_columns_ignored(self):
        df = pd.DataFrame({"A": [1], "B": [2]})
        result = normalizeColumns(df, ["A", "Z", "B"])
        assert list(result.columns) == ["A", "B"]

    def test_empty_order(self):
        df = pd.DataFrame({"B": [1], "A": [2]})
        result = normalizeColumns(df, [])
        assert list(result.columns) == ["A", "B"]

    def test_remaining_sorted(self):
        df = pd.DataFrame({"Z": [1], "M": [2], "A": [3], "B": [4]})
        result = normalizeColumns(df, ["B"])
        assert list(result.columns) == ["B", "A", "M", "Z"]
