from unittest.mock import patch

from sqlalchemy import func as realFunc
from sqlalchemy import literal

from main.app.prometheus.memory import PrometheusMemory as MemoryService
from main.models.memory import PrometheusMemory


USER_ID = 1

# fullTextSearch uses MySQL-only MATCH ... AGAINST, which cannot compile on the
# SQLite test fixture (see the skipped TestSearchFulltext class in
# test_memory_manager.py). Stub only the match expression with a constant so
# the real query shape, row mapping, and ORDER BY still execute.


class FakeMatch:
    def against(self, query, modifier=None):
        return literal(0.5)


class FakeFunc:
    def __getattr__(self, name):
        if name == "match":
            return lambda *cols, **kw: FakeMatch()
        return getattr(realFunc, name)


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


class TestFullTextSearchScoreFields:
    def test_score_is_match_value_relevance_is_stability(self, dbSession):
        # score column holds stability 7.0; stubbed match value is 0.5
        seedMemory(dbSession, "petrobras lider do setor de petroleo")
        with patch("main.app.prometheus.memory.func", FakeFunc()):
            results = MemoryService.fullTextSearch(dbSession, USER_ID, "petrobras", limit=10)
        assert len(results) == 1
        row = results[0]
        assert row["score"] == 0.5
        assert isinstance(row["score"], float)
        assert row["score"] != 7.0
        assert row["relevanceScore"] == 7.0
        assert row["score"] != row["relevanceScore"]
