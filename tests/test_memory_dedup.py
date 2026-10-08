from main.app.orunmila.memory import OrunmilaMemory as MemoryService, findSimilarKey
from main.models.memory import OrunmilaMemory


USER_ID = 1


def count_memories(db):
    return (
        db.query(OrunmilaMemory).filter(OrunmilaMemory.userId == USER_ID, OrunmilaMemory.archivedAt.is_(None)).count()
    )


def get_memory(db):
    return (
        db.query(OrunmilaMemory).filter(OrunmilaMemory.userId == USER_ID, OrunmilaMemory.archivedAt.is_(None)).first()
    )


class TestExactSameKeyUpdates:
    def test_exact_same_key_updates(self, dbSession):
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v2")
        assert result["status"] == "updated"
        assert result["memory"].memoryValue == "v2"


class TestSimilarKeyMerges:
    def test_similar_key_merges(self, dbSession):
        """Keys with fuzz.ratio > 80 should merge."""
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert count_memories(dbSession) == 1


class TestDifferentKeysNoMerge:
    def test_different_keys_no_merge(self, dbSession):
        """Keys with low similarity should not merge."""
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "vale", "v2")
        assert result["status"] == "created"
        assert count_memories(dbSession) == 2


class TestMergeBoostsScore:
    def test_merge_boosts_score(self, dbSession):
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v1")
        initial_score = get_memory(dbSession).score

        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert get_memory(dbSession).score == initial_score * 1.1


class TestMergeIncrementsAccess:
    def test_merge_increments_access(self, dbSession):
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras_preferencia", "v1")
        initial_access = get_memory(dbSession).accessCount

        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v2")
        assert get_memory(dbSession).accessCount == initial_access + 1


class TestThresholdBoundary:
    def test_threshold_boundary(self, dbSession):
        """Keys with fuzz.ratio <= 80 should not merge (strict >)."""
        # "a b" vs "a b c" -> fuzz.ratio = 75.0
        MemoryService.upsertMemory(dbSession, USER_ID, "a b", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "a b c", "v2")
        assert result["status"] == "created"

        # "a b c" vs "a b d" -> fuzz.ratio = 80.0, not > 80
        result2 = MemoryService.upsertMemory(dbSession, USER_ID, "a b d", "v3")
        assert result2["status"] == "created"

        assert count_memories(dbSession) == 3


class TestTypoAccentRegression:
    def test_typo_key_merges(self, dbSession):
        """Single-char typo still merges (fuzz.ratio > 80)."""
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "petrobraz preferencia", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert count_memories(dbSession) == 1

    def test_accent_key_merges(self, dbSession):
        """Accented key matches stored unaccented key via normalizeKey."""
        MemoryService.upsertMemory(dbSession, USER_ID, "acao preferencial", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "ação preferencial", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert count_memories(dbSession) == 1

    def test_case_key_merges(self, dbSession):
        """Uppercase key matches stored lowercase key via normalizeKey."""
        MemoryService.upsertMemory(dbSession, USER_ID, "petrobras preferencia", "v1")
        result = MemoryService.upsertMemory(dbSession, USER_ID, "PETROBRAS PREFERENCIA", "v2")
        assert result["status"] == "merged"
        assert result["memory"].memoryValue == "v2"
        assert count_memories(dbSession) == 1
