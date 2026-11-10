"""Quarterly export: canonical JSON payloads for glued and spaced quarter columns."""

import json
from pathlib import Path

import numpy as np
import pandas as pd

from main.app.scraper_b3.scraper import (
    QUARTERLY_COLUMN,
    attachQuarterlyPayload,
    normalizeQuarterLabel,
    quarterColumnPattern,
)


def quarterColumnsIn(df):
    return [col for col in df.columns if quarterColumnPattern.match(str(col))]


def test_normalizeQuarterLabel():
    assert normalizeQuarterLabel("1T2024") == "1T 2024"
    assert normalizeQuarterLabel("4T 2015") == "4T 2015"


def test_attachQuarterlyPayload_spaced_columns_use_canonical_keys():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["Petrobras"],
            "MARGEM BRUTA 1T 2024": [12.5],
        }
    )

    result = attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", "NOME", QUARTERLY_COLUMN]
    assert json.loads(result[QUARTERLY_COLUMN].iloc[0]) == {"MARGEM BRUTA 1T 2024": 12.5}
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_glued_columns_are_canonicalized_and_dropped():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "MARGEM BRUTA 4T2010": [12.5],
            "MARGEM BRUTA 1T2024": [np.nan],
        }
    )

    result = attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", QUARTERLY_COLUMN]
    assert json.loads(result[QUARTERLY_COLUMN].iloc[0]) == {"MARGEM BRUTA 4T 2010": 12.5}
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_mixed_forms_use_canonical_keys():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "MARGEM BRUTA 4T2010": [12.5, 1.0],
            "LUCRO LIQUIDO 1T 2024": [np.nan, 30.0],
        }
    )

    result = attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", QUARTERLY_COLUMN]
    assert json.loads(result[QUARTERLY_COLUMN].iloc[0]) == {"MARGEM BRUTA 4T 2010": 12.5}
    assert json.loads(result[QUARTERLY_COLUMN].iloc[1]) == {
        "MARGEM BRUTA 4T 2010": 1.0,
        "LUCRO LIQUIDO 1T 2024": 30.0,
    }
    assert quarterColumnsIn(result) == []


def test_attachQuarterlyPayload_empty_payload_is_none():
    df = pd.DataFrame({"TICKER": ["PETR4"], "MARGEM BRUTA 4T2010": [np.nan]})

    result = attachQuarterlyPayload(df)

    assert list(result.columns) == ["TICKER", QUARTERLY_COLUMN]
    assert result[QUARTERLY_COLUMN].iloc[0] is None


def test_attachQuarterlyPayload_without_quarter_columns_returns_df():
    df = pd.DataFrame({"TICKER": ["PETR4"], "RECEITA LIQUIDA 2024": [500.0]})

    assert attachQuarterlyPayload(df) is df


def test_scraper_has_no_b3_quarterly_sql():
    sourcePath = Path(__file__).resolve().parents[1] / "main/app/scraper_b3/scraper.py"

    assert "b3_quarterly" not in sourcePath.read_text(encoding="utf-8")
