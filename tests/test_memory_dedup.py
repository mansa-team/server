from main.app.prometheus.memory import PrometheusMemory, findSimilarKey
from main.models.memory import PrometheusMemory


USER_ID = 1


def _create_memory(db, key="petrobras preferencia", value="original value"):
    return PrometheusMemory.upsertMemory(db, USER_ID, key, value)


def _count_memories(db):
    return (
        db.query(PrometheusMemory)
        .filter(PrometheusMemory.userId == USER_ID, PrometheusMemory.archivedAt.is_(None))
        .count()
    )


def _get_memory(db):
    return (
        db.query(PrometheusMemory)
        .filter(PrometheusMemory.userId == USER_ID, PrometheusMemory.archivedAt.is_(None))
        .first()
    )


class TestExactSameKeyUpdates:
    def test_exact_same_key_updates(self, dbSession):
        _create_memory(dbSession, key="petrobras_preferencia", value="v1")
        result = PrometheusMemory.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v2")
        assert result["status"] == "updated"
        assert result["memory"].memoryValue == "v2"


class TestSimilarKeyMerges:
    def test_similar_key_merges(self, dbSession):
        """Keys with Jaccard > 0.8 should merge."""
        _create_memory(dbSession, key="petrobras_preferencia", value="v1")
        result = PrometheusMemory.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert _count_memories(dbSession) == 1


class TestDifferentKeysNoMerge:
    def test_different_keys_no_merge(self, dbSession):
        """Keys with low similarity should not merge."""
        _create_memory(dbSession, key="petrobras", value="v1")
        result = PrometheusMemory.upsertMemory(dbSession, USER_ID, "vale", "v2")
        assert result["status"] == "created"
        assert _count_memories(dbSession) == 2


class TestMergeBoostsScore:
    def test_merge_boosts_score(self, dbSession):
        _create_memory(dbSession, key="petrobras_preferencia", value="v1")
        initial_score = _get_memory(dbSession).baseScore

        PrometheusMemory.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert _get_memory(dbSession).baseScore == min(initial_score + 0.1, 1.0)


class TestMergeIncrementsAccess:
    def test_merge_increments_access(self, dbSession):
        _create_memory(dbSession, key="petrobras_preferencia", value="v1")
        initial_access = _get_memory(dbSession).accessCount

        PrometheusMemory.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert _get_memory(dbSession).accessCount == initial_access + 1


class TestThresholdBoundary:
    def test_threshold_boundary(self, dbSession):
        """Keys with Jaccard <= 0.8 should not merge."""
        # "a b" vs "a b c" -> intersection=2, union=3, sim=0.667
        _create_memory(dbSession, key="a b", value="v1")
        result = PrometheusMemory.upsertMemory(dbSession, USER_ID, "a b c", "v2")
        assert result["status"] == "created"

        # "a b c" vs "a b d" -> intersection=2, union=4, sim=0.5
        result2 = PrometheusMemory.upsertMemory(dbSession, USER_ID, "a b d", "v3")
        assert result2["status"] == "created"

        assert _count_memories(dbSession) == 3
