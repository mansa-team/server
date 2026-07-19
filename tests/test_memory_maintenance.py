import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from pytz import timezone

from main.app.prometheus.memory import PrometheusMemory as MemoryManager
from main.service.prometheus_service import (
    memoryMaintenance,
    DECAY_FACTORS,
    ARCHIVE_SCORE_THRESHOLD,
    ARCHIVE_DAYS_THRESHOLD,
)
from main.models.memory import PrometheusMemory


@pytest.fixture
def brt():
    return timezone("America/Sao_Paulo")


@pytest.fixture
def create_memories(dbSession, brt):
    """Helper to create memories with controlled baseScore, lastAccessedAt, accessCount."""

    def _create(userId, key, baseScore=1.0, daysOld=0, accessCount=0):
        now = brt.localize(datetime.now())
        lastAccessed = now - timedelta(days=daysOld)
        memory = PrometheusMemory(
            userId=userId,
            memoryKey=key,
            memoryValue=f"value_{key}",
            memoryType="context",
            source="inferred",
            baseScore=baseScore,
            accessCount=accessCount,
            lastAccessedAt=lastAccessed,
        )
        dbSession.add(memory)
        dbSession.commit()
        return memory

    return _create


class TestDecay:
    def test_active_memory_decays(self, dbSession, create_memories):
        mem = create_memories(1, "k1", baseScore=1.0, daysOld=30, accessCount=5)
        oldScore = mem.baseScore
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(oldScore * DECAY_FACTORS["context"], abs=1e-6)

    def test_zero_access_count_still_decays(self, dbSession, create_memories):
        """Decay applies to ALL active memories, not just accessed ones."""
        mem = create_memories(1, "k1", baseScore=0.8, daysOld=60, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(0.8 * DECAY_FACTORS["context"], abs=1e-6)

    def test_high_score_decays_proportionally(self, dbSession, create_memories):
        mem = create_memories(1, "k1", baseScore=0.5, daysOld=30, accessCount=2)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(0.5 * DECAY_FACTORS["context"], abs=1e-6)

    def test_very_low_score_stays_above_zero(self, dbSession, create_memories):
        """baseScore should never reach exactly 0 from decay alone."""
        mem = create_memories(1, "k1", baseScore=0.01, daysOld=30, accessCount=1)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore > 0

    def test_multiple_users_all_decayed(self, dbSession, create_memories):
        m1 = create_memories(1, "k1", baseScore=1.0, daysOld=30)
        m2 = create_memories(2, "k2", baseScore=0.9, daysOld=30)
        memoryMaintenance(dbSession)
        dbSession.refresh(m1)
        dbSession.refresh(m2)
        assert m1.baseScore == pytest.approx(1.0 * DECAY_FACTORS["context"], abs=1e-6)
        assert m2.baseScore == pytest.approx(0.9 * DECAY_FACTORS["context"], abs=1e-6)


class TestArchive:
    def test_dead_memory_archived(self, dbSession, create_memories, brt):
        """Score below threshold + accessCount=0 + 90+ days → archived."""
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_low_score_but_recent_not_archived(self, dbSession, create_memories):
        """Low score but accessed recently → not archived."""
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=10, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_zero_access_but_high_score_not_archived(self, dbSession, create_memories):
        """Zero access but score still above threshold → not archived."""
        mem = create_memories(1, "k1", baseScore=0.5, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_accessed_memory_not_archived(self, dbSession, create_memories):
        """Even with low score, if accessed → not archived."""
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=100, accessCount=3)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_already_archived_not_double_archived(self, dbSession, create_memories, brt):
        """Already archived memories are skipped."""
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=100, accessCount=0)
        mem.archivedAt = brt.localize(datetime.now() - timedelta(days=5))
        dbSession.commit()
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        # Should still be the original archive date, not re-processed
        assert mem.archivedAt is not None

    def test_multiple_users_independent_archive(self, dbSession, create_memories, brt):
        m1 = create_memories(1, "k1", baseScore=0.05, daysOld=100, accessCount=0)
        m2 = create_memories(2, "k2", baseScore=0.5, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(m1)
        dbSession.refresh(m2)
        assert m1.archivedAt is not None  # dead
        assert m2.archivedAt is None  # still alive


class TestDecayAndArchiveTogether:
    def test_decay_then_archive_check(self, dbSession, create_memories):
        """Decay happens first, then archive check with new scores."""
        # 0.12 * 0.90 = 0.108 — above threshold → NOT archived
        mem = create_memories(1, "k1", baseScore=0.12, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None
        assert mem.baseScore == pytest.approx(0.12 * DECAY_FACTORS["context"], abs=1e-6)

    def test_score_above_threshold_after_decay_not_archived(self, dbSession, create_memories):
        """Score that decays to >= threshold stays alive. 0.12 * 0.90 = 0.108 >= 0.1."""
        mem = create_memories(1, "k1", baseScore=0.12, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_score_just_below_threshold_archived(self, dbSession, create_memories):
        mem = create_memories(1, "k1", baseScore=ARCHIVE_SCORE_THRESHOLD - 0.001, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_days_just_below_threshold_not_archived(self, dbSession, create_memories):
        """89 days with low score → not archived (need > 90)."""
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=89, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_days_just_above_threshold_archived(self, dbSession, create_memories):
        mem = create_memories(1, "k1", baseScore=0.05, daysOld=ARCHIVE_DAYS_THRESHOLD + 1, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None


class TestEmptyDatabase:
    def test_no_memories_does_not_crash(self, dbSession):
        memoryMaintenance(dbSession)  # should not raise
