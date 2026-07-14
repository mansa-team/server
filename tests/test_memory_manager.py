import pytest
import numpy as np
from datetime import datetime, timezone
from main.app.prometheus.memory import MemoryManager, MEMORY_LIMIT_BASIC, MEMORY_LIMIT_EXTENDED
from main.models.memory import UserMemory
from main.utils.roles import Permission


class TestGetMemoryLimit:
    def test_basic_user(self):
        """Non-extended role gets basic limit."""
        assert MemoryManager.get_memory_limit(["USER"]) == MEMORY_LIMIT_BASIC

    def test_premium_user(self):
        """Premium user gets extended limit."""
        assert MemoryManager.get_memory_limit(["PREMIUM"]) == MEMORY_LIMIT_EXTENDED

    def test_admin_user(self):
        """Admin gets extended limit (has all permissions)."""
        assert MemoryManager.get_memory_limit(["ADMIN"]) == MEMORY_LIMIT_EXTENDED


class TestUpsertMemory:
    def test_create(self, dbSession):
        """Creates a new memory."""
        result = MemoryManager.upsert_memory(
            dbSession, user_id=1, key="fav_ticker", value="PETR4",
            memory_type="preference", source="explicit",
        )
        assert result["status"] == "created"
        assert result["memory"].memoryKey == "fav_ticker"
        assert result["memory"].memoryValue == "PETR4"

    def test_update(self, dbSession):
        """Updates existing memory when value changes."""
        MemoryManager.upsert_memory(dbSession, 1, "fav_ticker", "PETR4")
        result = MemoryManager.upsert_memory(dbSession, 1, "fav_ticker", "VALE3")
        assert result["status"] == "updated"
        assert result["memory"].memoryValue == "VALE3"
        assert result["memory"].accessCount == 1

    def test_unchanged(self, dbSession):
        """Returns unchanged when value is identical."""
        MemoryManager.upsert_memory(dbSession, 1, "fav_ticker", "PETR4")
        result = MemoryManager.upsert_memory(dbSession, 1, "fav_ticker", "PETR4")
        assert result["status"] == "unchanged"

    def test_limit_enforcement(self, dbSession):
        """Rejects new memory when limit reached."""
        for i in range(MEMORY_LIMIT_BASIC):
            MemoryManager.upsert_memory(dbSession, 1, f"key_{i}", f"val_{i}")

        result = MemoryManager.upsert_memory(
            dbSession, 1, "overflow", "blocked",
            user_roles=["USER"],
        )
        assert result["status"] == "limit_reached"
        assert result["limit"] == MEMORY_LIMIT_BASIC

    def test_limit_not_enforced_without_roles(self, dbSession):
        """No role check when user_roles not provided."""
        for i in range(MEMORY_LIMIT_BASIC):
            MemoryManager.upsert_memory(dbSession, 1, f"key_{i}", f"val_{i}")

        result = MemoryManager.upsert_memory(dbSession, 1, "extra", "bypassed")
        assert result["status"] == "created"

    def test_upsert_with_embedding(self, dbSession):
        """Stores embedding alongside memory."""
        emb = [0.1] * 384
        result = MemoryManager.upsert_memory(
            dbSession, 1, "emb_key", "with vector",
            embedding=emb,
        )
        assert result["status"] == "created"
        assert result["memory"].embedding is not None
        np.testing.assert_allclose(result["memory"].embedding, emb, atol=1e-5)


class TestCountMemories:
    def test_counts_active(self, dbSession):
        """Counts only non-archived memories."""
        MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        MemoryManager.upsert_memory(dbSession, 1, "k2", "v2")
        assert MemoryManager.count_memories(dbSession, 1) == 2

    def test_excludes_archived(self, dbSession):
        """Archived memories not counted."""
        MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        MemoryManager.upsert_memory(dbSession, 1, "k2", "v2")
        mem = dbSession.query(UserMemory).filter(UserMemory.memoryKey == "k1").first()
        from datetime import datetime
        mem.archivedAt = datetime.now(timezone.utc)
        dbSession.commit()
        assert MemoryManager.count_memories(dbSession, 1) == 1

    def test_counts_per_user(self, dbSession):
        """Counts are per-user."""
        MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        MemoryManager.upsert_memory(dbSession, 2, "k1", "v1")
        assert MemoryManager.count_memories(dbSession, 1) == 1
        assert MemoryManager.count_memories(dbSession, 2) == 1


class TestGetUserMemories:
    def test_returns_memories(self, dbSession):
        """Returns paginated memories."""
        MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        MemoryManager.upsert_memory(dbSession, 1, "k2", "v2")
        result = MemoryManager.get_user_memories(dbSession, 1)
        assert len(result) == 2
        assert result[0]["memoryKey"] in ("k1", "k2")

    def test_pagination(self, dbSession):
        """Offset and limit work."""
        for i in range(5):
            MemoryManager.upsert_memory(dbSession, 1, f"k{i}", f"v{i}")
        page = MemoryManager.get_user_memories(dbSession, 1, limit=2, offset=2)
        assert len(page) == 2

    def test_excludes_archived(self, dbSession):
        """Archived memories excluded."""
        MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        MemoryManager.upsert_memory(dbSession, 1, "k2", "v2")
        mem = dbSession.query(UserMemory).filter(UserMemory.memoryKey == "k1").first()
        from datetime import datetime
        mem.archivedAt = datetime.now(timezone.utc)
        dbSession.commit()
        result = MemoryManager.get_user_memories(dbSession, 1)
        assert len(result) == 1


class TestDeleteMemory:
    def test_soft_delete(self, dbSession):
        """Soft-deletes a memory."""
        result = MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        memory_id = result["memory"].id
        assert MemoryManager.delete_memory(dbSession, 1, memory_id) is True
        assert MemoryManager.count_memories(dbSession, 1) == 0

    def test_delete_nonexistent(self, dbSession):
        """Returns False for non-existent memory."""
        assert MemoryManager.delete_memory(dbSession, 1, 9999) is False

    def test_delete_wrong_user(self, dbSession):
        """Cannot delete another user's memory."""
        result = MemoryManager.upsert_memory(dbSession, 1, "k1", "v1")
        memory_id = result["memory"].id
        assert MemoryManager.delete_memory(dbSession, 2, memory_id) is False


@pytest.mark.skip(reason="SQLite does not support MySQL FULLTEXT MATCH AGAINST syntax")
class TestSearchFulltext:
    def test_search_after_create(self, dbSession):
        """FULLTEXT search finds matching memories (MySQL only)."""
        MemoryManager.upsert_memory(dbSession, 1, "ticker", "PETR4 preferido")
        MemoryManager.upsert_memory(dbSession, 1, "style", "Value Investing")
        results = MemoryManager._fulltext_search(dbSession, 1, "PETR4", 10)
        assert len(results) >= 1
        assert any("PETR4" in r["memoryValue"] for r in results)
