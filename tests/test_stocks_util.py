import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.stocks_api.util import categorizeColumns, parseDateRange
import pandas as pd
from fastapi import HTTPException


class TestCategorizeColumns:
    def test_categorize_columns_historical_only(self):
        columns = ["TICKER", "NOME", "LUCRO LIQUIDO 2020", "LUCRO LIQUIDO 2021", "RECEITA 2020", "RECEITA 2021"]
        historical, fundamental = categorizeColumns(columns)

        assert "LUCRO LIQUIDO" in historical
        assert 2020 in historical["LUCRO LIQUIDO"]
        assert 2021 in historical["LUCRO LIQUIDO"]
        assert "RECEITA" in historical

    def test_categorize_columns_fundamental_only(self):
        columns = ["TICKER", "NOME", "PRECO", "P/L", "ROE", "DY"]
        historical, fundamental = categorizeColumns(columns)

        assert len(historical) == 0
        assert "PRECO" in fundamental
        assert "P/L" in fundamental
        assert "ROE" in fundamental

    def test_categorize_columns_mixed(self):
        columns = ["TICKER", "NOME", "TIME", "PRECO", "P/L", "LUCRO LIQUIDO 2020", "LUCRO LIQUIDO 2021"]
        historical, fundamental = categorizeColumns(columns)

        assert "LUCRO LIQUIDO" in historical
        assert "PRECO" in fundamental
        assert "P/L" in fundamental

    def test_categorize_columns_excludes_special(self):
        columns = ["TICKER", "NOME", "TIME", "PRECO"]
        historical, fundamental = categorizeColumns(columns)

        assert "TICKER" not in fundamental
        assert "NOME" not in fundamental
        assert "TIME" not in fundamental

    def test_categorize_columns_empty(self):
        historical, fundamental = categorizeColumns([])
        assert len(historical) == 0
        assert len(fundamental) == 0


class TestParseDateRange:
    def test_parse_year_single(self):
        start, end = parseDateRange("2020")
        assert start.year == 2020
        assert start.month == 1
        assert start.day == 1
        assert end.year == 2020
        assert end.month == 12
        assert end.day == 31

    def test_parse_year_range(self):
        start, end = parseDateRange("2020,2023")
        assert start.year == 2020
        assert end.year == 2023

    def test_parse_year_none(self):
        start, end = parseDateRange(None)
        assert start is None
        assert end is None

    def test_parse_year_empty_string(self):
        start, end = parseDateRange("")
        assert start is None
        assert end is None

    def test_parse_month(self):
        start, end = parseDateRange("2026-06")
        assert start.month == 6
        assert start.day == 1
        assert end.month == 6
        assert end.day == 30

    def test_parse_full_date(self):
        start, end = parseDateRange("2026-06-15")
        assert start == end

    def test_parse_two_values(self):
        start, end = parseDateRange("2020-03,2023-09")
        assert start.year == 2020
        assert start.month == 3
        assert end.year == 2023
        assert end.month == 9

    def test_parse_three_values_raises(self):
        with pytest.raises(HTTPException) as exc:
            parseDateRange("2020,2021,2022")
        assert exc.value.status_code == 400
