from main.app.prometheus.memory import PrometheusMemory as MemoryService, findSimilarKey
from main.models.memory import PrometheusMemory


USER_ID = 1


def create_memory(db, key="petrobras preferencia", value="original value"):
    return MemoryService.upsertMemory(db, USER_ID, key, value)


def count_memories(db):
    return (
        db.query(PrometheusMemory)
        .filter(PrometheusMemory.userId == USER_ID, PrometheusMemory.archivedAt.is_(None))
        .count()
    )


def get_memory(db):
    return (
        db.query(PrometheusMemory)
        .filter(PrometheusMemory.userId == USER_ID, PrometheusMemory.archivedAt.is_(None))
        .first()
    )


class TestExactSameKeyUpdates:
    def test_exact_same_key_updates(self, dbSession):
        create_memory(dbSession, key="petrobras_preferencia", value="v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v2")
        assert result["status"] == "updated"
        assert result["memory"].memoryValue == "v2"


class TestSimilarKeyMerges:
    def test_similar_key_merges(self, dbSession):
        """Keys with Jaccard > 0.8 should merge."""
        create_memory(dbSession, key="petrobras_preferencia", value="v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert count_memories(dbSession) == 1


class TestDifferentKeysNoMerge:
    def test_different_keys_no_merge(self, dbSession):
        """Keys with low similarity should not merge."""
        create_memory(dbSession, key="petrobras", value="v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "vale", "v2")
        assert result["status"] == "created"
        assert count_memories(dbSession) == 2


class TestMergeBoostsScore:
    def test_merge_boosts_score(self, dbSession):
        create_memory(dbSession, key="petrobras_preferencia", value="v1")
        initial_score = get_memory(dbSession).score

        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert get_memory(dbSession).score == initial_score * 1.1


class TestMergeIncrementsAccess:
    def test_merge_increments_access(self, dbSession):
        create_memory(dbSession, key="petrobras_preferencia", value="v1")
        initial_access = get_memory(dbSession).accessCount

        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert get_memory(dbSession).accessCount == initial_access + 1


class TestThresholdBoundary:
    def test_threshold_boundary(self, dbSession):
        """Keys with Jaccard <= 0.8 should not merge."""
        # "a b" vs "a b c" -> intersection=2, union=3, sim=0.667
        create_memory(dbSession, key="a b", value="v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "a b c", "v2")
        assert result["status"] == "created"

        # "a b c" vs "a b d" -> intersection=2, union=4, sim=0.5
        result2 = MemoryService.upsertMemory(dbSession, USER_ID, "a b d", "v3")
        assert result2["status"] == "created"

        assert count_memories(dbSession) == 3
