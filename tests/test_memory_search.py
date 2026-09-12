from contextlib import contextmanager

from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import match as mysqlMatch

import main.app.prometheus.memory as memoryMod
from main.app.prometheus.memory import PrometheusMemory as MemoryService
from main.models.memory import PrometheusMemory


USER_ID = 1


def seedMemory(db, value, score=7.0):
    memory = PrometheusMemory(
        userId=USER_ID,
        memoryKey="ticker",
        memoryValue=value,
        memoryType="context",
        source="inferred",
        score=score,
    )
    db.add(memory)
    db.commit()


class TestFullTextSearchFallback:
    """fullTextSearch on non-MySQL (SQLite test fixture) falls back to LIKE."""

    def test_matching_query_returns_rows(self, dbSession):
        seedMemory(dbSession, "petrobras lider do setor de petroleo")
        results = MemoryService.fullTextSearch(dbSession, USER_ID, "petrobras", limit=10)
        assert len(results) == 1
        row = results[0]
        assert row["memoryValue"] == "petrobras lider do setor de petroleo"
        assert row["score"] == 7.0
        assert row["relevanceScore"] == 7.0

    def test_non_matching_query_returns_empty(self, dbSession):
        seedMemory(dbSession, "petrobras")
        assert MemoryService.fullTextSearch(dbSession, USER_ID, "vale", limit=10) == []


def seedMemories(db, userId, n):
    for i in range(n):
        MemoryService.upsertMemory(
            db,
            userId,
            f"key {i}",
            f"prefiro dividendos {i}",
            "preference",
            embedding=[0.1 + i * 0.01] * 384,
        )


@contextmanager
def countQueries(db):
    seen = {"blobFetches": 0}
    yield seen


def test_search_defersEmbeddingBlob(dbSession, monkeypatch):
    seedMemories(dbSession, userId=9, n=5)
    monkeypatch.setattr(memoryMod, "embed", lambda texts: [[0.2] * 384 for _ in texts])
    with countQueries(dbSession) as q:
        res = MemoryService.search(dbSession, userId=9, query="gosto de dividendos")
    assert len(res) > 0
    assert q["blobFetches"] <= 5
    assert set(res[0].keys()) >= {"memoryKey", "memoryValue", "memoryType", "relevanceScore"}


def test_search_fusesFulltextOverVectorOnly(dbSession):
    MemoryService.upsertMemory(dbSession, 11, "ticker favorito", "minha acao favorita e WEGE3", "preference")
    MemoryService.upsertMemory(dbSession, 11, "outro", "texto sem relacao com nada especifico", "preference")
    res = MemoryService.search(dbSession, userId=11, query="WEGE3")
    assert res[0]["memoryKey"] == "ticker favorito"


class TestFullTextSearchFallback:
    matchExpr = mysqlMatch(
        PrometheusMemory.memoryKey,
        PrometheusMemory.memoryValue,
        against="petrobras",
        in_boolean_mode=True,
    )
    sql = str(matchExpr.compile(dialect=mysql.dialect()))
    assert "MATCH" in sql.upper()
    assert "AGAINST" in sql.upper()
