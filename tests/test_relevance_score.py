import math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
from main.app.prometheus.vector import getRelevanceScore


SAO_PAULO_TZ = ZoneInfo("America/Sao_Paulo")
NOW = datetime(2026, 7, 14, 12, 0, 0, tzinfo=SAO_PAULO_TZ)


class _FakeMemory:
    def __init__(self, score=7.0, lastAccessedAt=None):
        self.score = score
        self.lastAccessedAt = lastAccessedAt or NOW


class TestTimeDecay:
    def test_just_accessed_has_full_score(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW)
        score = getRelevanceScore(mem, NOW)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_one_day_old(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=1))
        score = getRelevanceScore(mem, NOW)
        # R = e^(-1/7) ≈ 0.867
        assert score == pytest.approx(0.867, abs=0.05)

    def test_seven_days_old(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=7))
        score = getRelevanceScore(mem, NOW)
        # R = e^(-7/7) = e^(-1) ≈ 0.368
        assert score == pytest.approx(0.368, abs=0.05)

    def test_thirty_days_old(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=30))
        score = getRelevanceScore(mem, NOW)
        # R = e^(-30/7) ≈ 0.013
        assert score == pytest.approx(0.013, abs=0.01)

    def test_ninety_days_old(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=90))
        score = getRelevanceScore(mem, NOW)
        # R = e^(-90/7) ≈ 3.3e-6, essentially 0
        assert score < 0.01

    def test_one_year_old(self):
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=365))
        score = getRelevanceScore(mem, NOW)
        assert score < 0.001

    def test_score_always_positive(self):
        for days in [0, 1, 7, 30, 90, 365, 730]:
            mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=days))
            score = getRelevanceScore(mem, NOW)
            assert score > 0


class TestStabilityImpact:
    def test_high_stability_beats_low_same_age(self):
        old = NOW - timedelta(days=14)
        high = _FakeMemory(score=14.0, lastAccessedAt=old)
        low = _FakeMemory(score=3.0, lastAccessedAt=old)
        # R_high = e^(-14/14) = 0.368, R_low = e^(-14/3) ≈ 0.0087
        assert getRelevanceScore(high, NOW) > getRelevanceScore(low, NOW)

    def test_sticky_memory_outlasts_ephemeral(self):
        """A preference (S=14) at 4 days beats a context (S=3) at 1 day.
        Crossover: X/14 = Y/3 → X = 14Y/3 ≈ 4.67. At 4 days: e^(-4/14) ≈ 0.751 > e^(-1/3) ≈ 0.717."""
        sticky_4d = _FakeMemory(score=14.0, lastAccessedAt=NOW - timedelta(days=4))
        ephemeral_1d = _FakeMemory(score=3.0, lastAccessedAt=NOW - timedelta(days=1))
        assert getRelevanceScore(sticky_4d, NOW) > getRelevanceScore(ephemeral_1d, NOW)

    def test_ephemeral_old_loses_to_sticky_new(self):
        """An old ephemeral memory loses to a fresh sticky one."""
        ephemeral_old = _FakeMemory(score=3.0, lastAccessedAt=NOW - timedelta(days=30))
        sticky_new = _FakeMemory(score=14.0, lastAccessedAt=NOW)
        assert getRelevanceScore(sticky_new, NOW) > getRelevanceScore(ephemeral_old, NOW)

    def test_higher_stability_always_wins_at_same_age(self):
        """With same access time, higher stability always produces higher retention."""
        t = NOW - timedelta(days=14)
        a = _FakeMemory(score=3.0, lastAccessedAt=t)
        b = _FakeMemory(score=14.0, lastAccessedAt=t)
        assert getRelevanceScore(b, NOW) > getRelevanceScore(a, NOW)


class TestDecayMonotonicity:
    def test_older_always_lower_score(self):
        scores = []
        for days in [0, 1, 7, 14, 30, 60, 90, 180, 365]:
            mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=days))
            scores.append(getRelevanceScore(mem, NOW))
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Score at day {i} should be >= day {i + 1}"

    def test_never_accessed_uses_stability(self):
        """A memory with no lastAccessedAt uses score as stability."""
        mem = _FakeMemory(score=7.0, lastAccessedAt=None)
        score = getRelevanceScore(mem, NOW)
        # No lastAccessedAt falls back to createdAt, which defaults to NOW
        # so R ≈ 1.0
        assert score == pytest.approx(1.0, abs=0.01)


class TestNoCronNeeded:
    def test_same_memory_same_time_same_score(self):
        """Scores are deterministic — no cron mutation needed."""
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=14))
        s1 = getRelevanceScore(mem, NOW)
        s2 = getRelevanceScore(mem, NOW)
        assert s1 == s2

    def test_different_times_different_scores(self):
        """Same memory at different points in time yields different scores."""
        mem = _FakeMemory(score=7.0, lastAccessedAt=NOW - timedelta(days=7))
        score_now = getRelevanceScore(mem, NOW)
        score_later = getRelevanceScore(mem, NOW + timedelta(days=30))
        assert score_now > score_later
