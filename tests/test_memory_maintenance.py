import math
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from pytz import timezone

from main.app.prometheus.memory import PrometheusMemory as MemoryManager
from main.service.prometheus_service import (
    memoryMaintenance,
    ARCHIVE_SCORE_THRESHOLD,
)
from main.models.memory import PrometheusMemory


@pytest.fixture
def brt():
    return timezone("America/Sao_Paulo")


@pytest.fixture
def create_memories(dbSession, brt):
    """Helper to create memories with controlled stability, lastAccessedAt, accessCount."""

    def _create(userId, key, baseScore=7.0, daysOld=0, accessCount=0):
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


class TestEbbinghausRetention:
    def test_retention_formula(self):
        """Verify R = e^(-t/S) produces expected values."""
        assert math.exp(-0 / 7.0) == pytest.approx(1.0, abs=1e-6)
        assert math.exp(-1 / 7.0) == pytest.approx(0.8669, abs=1e-3)
        assert math.exp(-7 / 7.0) == pytest.approx(0.3679, abs=1e-3)
        assert math.exp(-30 / 7.0) == pytest.approx(0.0131, abs=1e-3)

    def test_high_stability_forgotten_slowly(self):
        """High stability (S=14) retains more than low stability (S=3) at same age."""
        s_high = math.exp(-7 / 14.0)  # ~0.607
        s_low = math.exp(-7 / 3.0)   # ~0.097
        assert s_high > s_low


class TestArchive:
    def test_dead_memory_archived(self, dbSession, create_memories):
        """Retention below threshold + accessCount=0 → archived."""
        # S=7.0, 90 days old → R = e^(-90/7) ≈ 3.3e-6 < 0.1
        mem = create_memories(1, "k1", baseScore=7.0, daysOld=90, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_low_stability_old_memory_archived(self, dbSession, create_memories):
        """Low stability (S=3) memory archived after 30 days: R=e^(-30/3)≈0.000045."""
        mem = create_memories(1, "k1", baseScore=3.0, daysOld=30, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_high_stability_old_memory_not_archived(self, dbSession, create_memories):
        """High stability (S=14) at 30 days: R=e^(-30/14)≈0.117 > 0.1."""
        mem = create_memories(1, "k1", baseScore=14.0, daysOld=30, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_low_score_but_recent_not_archived(self, dbSession, create_memories):
        """Low stability but accessed recently → not archived."""
        # S=3.0, 1 day old: R=e^(-1/3)≈0.717 > 0.1
        mem = create_memories(1, "k1", baseScore=3.0, daysOld=1, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_zero_access_but_high_stability_not_archived(self, dbSession, create_memories):
        """Zero access but high stability keeps retention above threshold."""
        # S=14, 20 days: R=e^(-20/14)≈0.239 > 0.1
        mem = create_memories(1, "k1", baseScore=14.0, daysOld=20, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_accessed_memory_not_archived(self, dbSession, create_memories):
        """Even with low retention, if accessCount > 0 → not archived."""
        # S=3, 30 days → R≈0.000045, but accessCount=5
        mem = create_memories(1, "k1", baseScore=3.0, daysOld=30, accessCount=5)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is None

    def test_already_archived_not_double_archived(self, dbSession, create_memories, brt):
        """Already archived memories are skipped."""
        mem = create_memories(1, "k1", baseScore=7.0, daysOld=100, accessCount=0)
        mem.archivedAt = brt.localize(datetime.now() - timedelta(days=5))
        dbSession.commit()
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_multiple_users_independent_archive(self, dbSession, create_memories):
        m1 = create_memories(1, "k1", baseScore=3.0, daysOld=30, accessCount=0)  # low S → archived
        m2 = create_memories(2, "k2", baseScore=14.0, daysOld=30, accessCount=0)  # high S → kept
        memoryMaintenance(dbSession)
        dbSession.refresh(m1)
        dbSession.refresh(m2)
        assert m1.archivedAt is not None
        assert m2.archivedAt is None


class TestArchiveEdgeCases:
    def test_score_at_exactly_threshold_not_archived(self, dbSession, create_memories):
        """Retention exactly at threshold is not archived (< not <=)."""
        # S=7.0, find t where R=e^(-t/7) ≈ 0.1 → t ≈ -7*ln(0.1) ≈ 16.12 days
        mem = create_memories(1, "k1", baseScore=7.0, daysOld=16, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        # R = e^(-16/7) ≈ 0.1029 > 0.1
        assert mem.archivedAt is None

    def test_retention_just_below_threshold_archived(self, dbSession, create_memories):
        """Retention just below 0.1 → archived."""
        # S=7.0, 17 days: R=e^(-17/7)≈0.0889 < 0.1
        mem = create_memories(1, "k1", baseScore=7.0, daysOld=17, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.archivedAt is not None

    def test_min_stability_floor(self, dbSession, create_memories):
        """baseScore=0.0 is clamped to 0.1 stability floor."""
        mem = create_memories(1, "k1", baseScore=0.0, daysOld=100, accessCount=0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        # R = e^(-100/0.1) ≈ 0 → archived
        assert mem.archivedAt is not None


class TestEmptyDatabase:
    def test_no_memories_does_not_crash(self, dbSession):
        memoryMaintenance(dbSession)  # should not raise
