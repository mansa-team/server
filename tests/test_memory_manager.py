import pytest
import numpy as np
from datetime import datetime, timezone
from main.app.prometheus.memory import MemoryManager, MEMORY_LIMIT_BASIC, MEMORY_LIMIT_EXTENDED
from main.models.memory import UserMemory


class TestGetMemoryLimit:
    def test_basic_user(self):
        assert MemoryManager.getMemoryLimit(["USER"]) == MEMORY_LIMIT_BASIC

    def test_premium_user(self):
        assert MemoryManager.getMemoryLimit(["PREMIUM"]) == MEMORY_LIMIT_EXTENDED

    def test_admin_user(self):
        assert MemoryManager.getMemoryLimit(["ADMIN"]) == MEMORY_LIMIT_EXTENDED


class TestUpsertMemory:
    def test_create(self, dbSession):
        result = MemoryManager.upsertMemory(
            dbSession,
            userId=1,
            key="fav_ticker",
            value="PETR4",
            memoryType="preference",
            source="explicit",
        )
        assert result["status"] == "created"
        assert result["memory"].memoryKey == "fav_ticker"
        assert result["memory"].memoryValue == "PETR4"

    def test_update(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "fav_ticker", "PETR4")
        result = MemoryManager.upsertMemory(dbSession, 1, "fav_ticker", "VALE3")
        assert result["status"] == "updated"
        assert result["memory"].memoryValue == "VALE3"
        assert result["memory"].accessCount == 1

    def test_unchanged(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "fav_ticker", "PETR4")
        result = MemoryManager.upsertMemory(dbSession, 1, "fav_ticker", "PETR4")
        assert result["status"] == "unchanged"

    def test_limit_enforcement(self, dbSession):
        for i in range(MEMORY_LIMIT_BASIC):
            MemoryManager.upsertMemory(dbSession, 1, f"key_{i}", f"val_{i}")

        result = MemoryManager.upsertMemory(
            dbSession,
            1,
            "overflow",
            "blocked",
            userRoles=["USER"],
        )
        assert result["status"] == "limit_reached"
        assert result["limit"] == MEMORY_LIMIT_BASIC

    def test_limit_not_enforced_without_roles(self, dbSession):
        for i in range(MEMORY_LIMIT_BASIC):
            MemoryManager.upsertMemory(dbSession, 1, f"key_{i}", f"val_{i}")

        result = MemoryManager.upsertMemory(dbSession, 1, "extra", "bypassed")
        assert result["status"] == "created"

    def test_upsert_with_embedding(self, dbSession):
        emb = [0.1] * 384
        result = MemoryManager.upsertMemory(
            dbSession,
            1,
            "emb_key",
            "with vector",
            embedding=emb,
        )
        assert result["status"] == "created"
        assert result["memory"].embedding is not None
        np.testing.assert_allclose(result["memory"].embedding, emb, atol=1e-5)


class TestCountMemories:
    def test_counts_active(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        MemoryManager.upsertMemory(dbSession, 1, "k2", "v2")
        assert MemoryManager.countMemories(dbSession, 1) == 2

    def test_excludes_archived(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        MemoryManager.upsertMemory(dbSession, 1, "k2", "v2")
        mem = dbSession.query(UserMemory).filter(UserMemory.memoryKey == "k1").first()
        mem.archivedAt = datetime.now(timezone.utc)
        dbSession.commit()
        assert MemoryManager.countMemories(dbSession, 1) == 1

    def test_counts_per_user(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        MemoryManager.upsertMemory(dbSession, 2, "k1", "v1")
        assert MemoryManager.countMemories(dbSession, 1) == 1
        assert MemoryManager.countMemories(dbSession, 2) == 1


class TestGetUserMemories:
    def test_returns_memories(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        MemoryManager.upsertMemory(dbSession, 1, "k2", "v2")
        result = MemoryManager.getUserMemories(dbSession, 1)
        assert len(result) == 2
        assert result[0]["memoryKey"] in ("k1", "k2")

    def test_pagination(self, dbSession):
        for i in range(5):
            MemoryManager.upsertMemory(dbSession, 1, f"k{i}", f"v{i}")
        page = MemoryManager.getUserMemories(dbSession, 1, limit=2, offset=2)
        assert len(page) == 2

    def test_excludes_archived(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        MemoryManager.upsertMemory(dbSession, 1, "k2", "v2")
        mem = dbSession.query(UserMemory).filter(UserMemory.memoryKey == "k1").first()
        mem.archivedAt = datetime.now(timezone.utc)
        dbSession.commit()
        result = MemoryManager.getUserMemories(dbSession, 1)
        assert len(result) == 1


class TestDeleteMemory:
    def test_soft_delete(self, dbSession):
        result = MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        memoryId = result["memory"].id
        assert MemoryManager.deleteMemory(dbSession, 1, memoryId) is True
        assert MemoryManager.countMemories(dbSession, 1) == 0

    def test_delete_nonexistent(self, dbSession):
        assert MemoryManager.deleteMemory(dbSession, 1, 9999) is False

    def test_delete_wrong_user(self, dbSession):
        result = MemoryManager.upsertMemory(dbSession, 1, "k1", "v1")
        memoryId = result["memory"].id
        assert MemoryManager.deleteMemory(dbSession, 2, memoryId) is False


@pytest.mark.skip(reason="SQLite does not support MySQL FULLTEXT MATCH AGAINST syntax")
class TestSearchFulltext:
    def test_search_after_create(self, dbSession):
        MemoryManager.upsertMemory(dbSession, 1, "ticker", "PETR4 preferido")
        MemoryManager.upsertMemory(dbSession, 1, "style", "Value Investing")
        results = MemoryManager._fulltextSearch(dbSession, 1, "PETR4", 10)
        assert len(results) >= 1
        assert any("PETR4" in r["memoryValue"] for r in results)
