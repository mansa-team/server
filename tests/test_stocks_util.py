import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.stocks_api.util import categorizeColumns, parseYearInput
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


class TestParseYearInput:
    def test_parse_year_single(self):
        start, end = parseYearInput("2020")
        assert start == 2020
        assert end == 2020

    def test_parse_year_range(self):
        start, end = parseYearInput("2020,2023")
        assert start == 2020
        assert end == 2023

    def test_parse_year_none(self):
        start, end = parseYearInput(None)
        assert start is None
        assert end is None

    def test_parse_year_empty_string(self):
        start, end = parseYearInput("")
        assert start is None
        assert end is None

    def test_parse_year_with_spaces(self):
        start, end = parseYearInput("2020 , 2023")
        assert start == 2020
        assert end == 2023

    def test_parse_year_invalid_format(self):
        with pytest.raises(HTTPException) as exc:
            parseYearInput("2020,2021,2022")
        assert exc.value.status_code == 400

    def test_parse_year_invalid_non_digit(self):
        with pytest.raises(ValueError):
            parseYearInput("abc")