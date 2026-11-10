"""Quarterly export: canonical JSON payloads for glued and spaced quarter columns."""

import json
import re
from pathlib import Path

import pandas as pd

from main.app.scraper_b3.scraper import B3Scraper, Config


def quarterColumnsIn(df):
    pattern = re.compile(r"^(?P<metric>.+) (?P<quarter>[1-4]T)\s*(?P<year>\d{4})$")
    return [col for col in df.columns if pattern.match(str(col))]


def test_scrapeStocks_prepares_quarterly_json_for_both_exports():
    scraper = object.__new__(B3Scraper)
    scraper.stats = {}
    scraper.scraperDate = "2026-11-05 18:30:00"
    scraper.getInitialData = lambda: pd.DataFrame(
        {"TICKER": ["PETR4"], "NOME": ["Petrobras"], "RECEITA LIQUIDA 2024": [500.0]},
        index=["PETR4"],
    )
    scraper.processTicker = lambda ticker, row, stocksDF: {"TICKER": ticker, "MARGEM BRUTA 4T2010": 12.5}
    captured = {}
    scraper.exportJson = lambda df: captured.setdefault("json", df)
    scraper.exportMysql = lambda df: captured.setdefault("mysql", df)

    scraper.scrapeStocks(maxWorkers=1)

    for name in ("json", "mysql"):
        df = captured[name]
        assert "HISTORICO TRIMESTRAL" in df.columns
        assert quarterColumnsIn(df) == []
        assert json.loads(df["HISTORICO TRIMESTRAL"].iloc[0]) == {"MARGEM BRUTA 4T 2010": 12.5}


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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement, parameters=None):
        self.statements.append(str(statement))
        return _ScalarResult(self.dataType)


class _Engine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return self.conn


def _exportMysql(monkeypatch, dataType):
    conn = _QueryConn(dataType)
    scraper = object.__new__(B3Scraper)
    scraper.engine = _Engine(conn)
    scraper.scraperDate = "2026-11-05 18:30:00"
    df = pd.DataFrame({"TICKER": ["PETR4"], "COTACAO PADRAO": ['{"a": 1}'], "HISTORICO TRIMESTRAL": [None]})
    existing = pd.DataFrame(columns=["TICKER", "COTACAO PADRAO", "HISTORICO TRIMESTRAL"])
    monkeypatch.setattr(Config.SCRAPER, "MYSQL", True)
    monkeypatch.setattr(pd, "read_sql", lambda *args, **kwargs: existing)
    monkeypatch.setattr(pd.DataFrame, "to_sql", lambda *args, **kwargs: None)
    scraper.exportMysql(df)
    return conn


def test_exportMysql_skips_alter_when_already_longtext(monkeypatch):
    conn = _exportMysql(monkeypatch, "longtext")

    assert not any("MODIFY COLUMN" in statement for statement in conn.statements)
    assert any("information_schema.COLUMNS" in statement for statement in conn.statements)


def test_exportMysql_alters_when_type_is_not_longtext(monkeypatch):
    conn = _exportMysql(monkeypatch, "text")

    alters = [statement for statement in conn.statements if "MODIFY COLUMN" in statement]
    assert len(alters) == 1
    assert "`COTACAO PADRAO` LONGTEXT NULL" in alters[0]
