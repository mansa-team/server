"""Quarterly export: canonical JSON payloads for glued and spaced quarter columns."""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from main.app.scraper_b3.scraper import B3Scraper


scraper = object.__new__(B3Scraper)


def quarterColumnsIn(df):
    pattern = re.compile(r"^(?P<metric>.+) (?P<quarter>[1-4]T)\s*(?P<year>\d{4})$")
    return [col for col in df.columns if pattern.match(str(col))]


def test_attachQuarterlyPayload_spaced_columns_use_canonical_keys():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["Petrobras"],
            "MARGEM BRUTA 1T 2024": [12.5],
        }
    )

    result = scraper.attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", "NOME", "HISTORICO TRIMESTRAL"]
    assert json.loads(result["HISTORICO TRIMESTRAL"].iloc[0]) == {"MARGEM BRUTA 1T 2024": 12.5}
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_glued_columns_are_canonicalized_and_dropped():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "MARGEM BRUTA 4T2010": [12.5],
            "MARGEM BRUTA 1T2024": [np.nan],
        }
    )

    result = scraper.attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", "HISTORICO TRIMESTRAL"]
    assert json.loads(result["HISTORICO TRIMESTRAL"].iloc[0]) == {"MARGEM BRUTA 4T 2010": 12.5}
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_mixed_forms_use_canonical_keys():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "MARGEM BRUTA 4T2010": [12.5, 1.0],
            "LUCRO LIQUIDO 1T 2024": [np.nan, 30.0],
        }
    )

    result = scraper.attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", "HISTORICO TRIMESTRAL"]
    assert json.loads(result["HISTORICO TRIMESTRAL"].iloc[0]) == {"MARGEM BRUTA 4T 2010": 12.5}
    assert json.loads(result["HISTORICO TRIMESTRAL"].iloc[1]) == {
        "MARGEM BRUTA 4T 2010": 1.0,
        "LUCRO LIQUIDO 1T 2024": 30.0,
    }
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_empty_payload_is_none():
    df = pd.DataFrame({"TICKER": ["PETR4"], "MARGEM BRUTA 4T2010": [np.nan]})

    result = scraper.attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", "HISTORICO TRIMESTRAL"]
    assert result["HISTORICO TRIMESTRAL"].iloc[0] is None


def test_attachQuarterlyPayload_without_quarter_columns_returns_df():
    df = pd.DataFrame({"TICKER": ["PETR4"], "RECEITA LIQUIDA 2024": [500.0]})

    assert scraper.attachQuarterlyPayload(df) is df


def test_scraper_has_no_b3_quarterly_sql():
    sourcePath = Path(__file__).resolve().parents[1] / "main/app/scraper_b3/scraper.py"

    assert "b3_quarterly" not in sourcePath.read_text(encoding="utf-8")


class _ScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class _QueryConn:
    def __init__(self, dataType):
        self.dataType = dataType
        self.statements = []

    def execute(self, statement, parameters=None):
        self.statements.append(str(statement))
        return _ScalarResult(self.dataType)


def test_ensureLongTextColumns_skips_alter_when_already_longtext():
    conn = _QueryConn("longtext")
    df = pd.DataFrame({"TICKER": ["PETR4"], "COTACAO PADRAO": ['{"a": 1}']})

    scraper.ensureLongTextColumns(conn, df)

    assert not any("MODIFY COLUMN" in statement for statement in conn.statements)
    assert any("information_schema.COLUMNS" in statement for statement in conn.statements)


def test_ensureLongTextColumns_alters_when_type_is_not_longtext():
    conn = _QueryConn("text")
    df = pd.DataFrame({"TICKER": ["PETR4"], "COTACAO PADRAO": ['{"a": 1}']})

    scraper.ensureLongTextColumns(conn, df)

    alters = [statement for statement in conn.statements if "MODIFY COLUMN" in statement]
    assert len(alters) == 1
    assert "`COTACAO PADRAO` LONGTEXT NULL" in alters[0]
