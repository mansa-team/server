from sqlalchemy.dialects import mysql
from sqlalchemy.dialects.mysql import match as mysqlMatch

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

    def test_mysql_path_generates_match_against(self):
        matchExpr = mysqlMatch(
            PrometheusMemory.memoryKey,
            PrometheusMemory.memoryValue,
            against="petrobras",
            in_boolean_mode=True,
        )
        sql = str(matchExpr.compile(dialect=mysql.dialect()))
        assert "MATCH" in sql.upper()
        assert "AGAINST" in sql.upper()
