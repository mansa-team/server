"""Tests for main/app/stocks_api/util.py."""

from datetime import date

import pandas as pd
import pytest
from fastapi import HTTPException
from main.app.stocks_api.util import categorizeColumns, parseDate, parseDateRange


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

    def test_malformed_raises_400(self):
        with pytest.raises(HTTPException) as exc_info:
            parseDateRange("bogus")
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid date format. Use YYYY-MM-DD"


class TestParseDate:
    def test_year(self):
        assert parseDate("2022") == date(2022, 1, 1)
        assert parseDate("2022", end=True) == date(2022, 12, 31)

    def test_month(self):
        assert parseDate("2022-06") == date(2022, 6, 1)
        assert parseDate("2022-06", end=True) == date(2022, 6, 30)

    def test_full_date(self):
        assert parseDate("2022-06-15") == date(2022, 6, 15)

    @pytest.mark.parametrize("bad", ["bogus", "2024-13", "2024-13-01", "2024-06-31"])
    def test_malformed_raises_400(self, bad):
        with pytest.raises(HTTPException) as exc_info:
            parseDate(bad)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Invalid date format. Use YYYY-MM-DD"
