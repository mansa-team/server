import math
from datetime import datetime, timedelta
import pytz
import pytest
from main.utils.vector import getRelevanceScore


SAO_PAULO_TZ = pytz.timezone("America/Sao_Paulo")
NOW = SAO_PAULO_TZ.localize(datetime(2026, 7, 14, 12, 0, 0))


class _FakeMemory:
    def __init__(self, baseScore=1.0, lastAccessedAt=None):
        self.baseScore = baseScore
        self.lastAccessedAt = lastAccessedAt or NOW


class TestTimeDecay:
    def test_just_accessed_has_full_score(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW)
        score = getRelevanceScore(mem, NOW)
        assert score == pytest.approx(1.0, abs=0.01)

    def test_one_day_old(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=1))
        score = getRelevanceScore(mem, NOW)
        assert 0.6 < score < 0.80

    def test_seven_days_old(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=7))
        score = getRelevanceScore(mem, NOW)
        assert 0.35 < score < 0.70

    def test_thirty_days_old(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=30))
        score = getRelevanceScore(mem, NOW)
        assert 0.20 < score < 0.45

    def test_ninety_days_old(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=90))
        score = getRelevanceScore(mem, NOW)
        assert 0.10 < score < 0.30

    def test_one_year_old(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=365))
        score = getRelevanceScore(mem, NOW)
        assert 0.05 < score < 0.20

    def test_score_always_positive(self):
        for days in [0, 1, 7, 30, 90, 365, 730]:
            mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=days))
            score = getRelevanceScore(mem, NOW)
            assert score > 0


class TestBaseScoreImpact:
    def test_high_base_beats_low_base_same_age(self):
        old = NOW - timedelta(days=30)
        high = _FakeMemory(baseScore=1.0, lastAccessedAt=old)
        low = _FakeMemory(baseScore=0.3, lastAccessedAt=old)
        assert getRelevanceScore(high, NOW) > getRelevanceScore(low, NOW)

    def test_frequently_used_survives_longer(self):
        """A memory accessed 10x (baseScore 1.0) should still outrank
        a memory accessed once (baseScore 0.1) even if the former is older."""
        popular_old = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=30))
        rare_new = _FakeMemory(baseScore=0.1, lastAccessedAt=NOW)
        # Popularity wins: 10x usage keeps it relevant despite age
        assert getRelevanceScore(popular_old, NOW) > getRelevanceScore(rare_new, NOW)

    def test_rare_old_loses_to_popular_new(self):
        """A rarely-used old memory should lose to a popular fresh one."""
        rare_old = _FakeMemory(baseScore=0.1, lastAccessedAt=NOW - timedelta(days=60))
        popular_new = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW)
        assert getRelevanceScore(popular_new, NOW) > getRelevanceScore(rare_old, NOW)

    def test_score_capped_at_one(self):
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW)
        score = getRelevanceScore(mem, NOW)
        assert score <= 1.0

    def test_equal_age_higher_base_wins(self):
        """With same access time, higher baseScore always wins."""
        t = NOW - timedelta(days=14)
        a = _FakeMemory(baseScore=0.3, lastAccessedAt=t)
        b = _FakeMemory(baseScore=0.9, lastAccessedAt=t)
        assert getRelevanceScore(b, NOW) > getRelevanceScore(a, NOW)


class TestDecayMonotonicity:
    def test_older_always_lower_score(self):
        scores = []
        for days in [0, 1, 7, 14, 30, 60, 90, 180, 365]:
            mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=days))
            scores.append(getRelevanceScore(mem, NOW))
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Score at day {i} should be >= day {i + 1}"

    def test_never_accessed_uses_full_base(self):
        """A memory with no lastAccessedAt should use baseScore as-is."""
        mem = _FakeMemory(baseScore=0.7, lastAccessedAt=None)
        score = getRelevanceScore(mem, NOW)
        assert score == pytest.approx(0.7, abs=0.01)


class TestNoCronNeeded:
    def test_same_memory_same_time_same_score(self):
        """Scores are deterministic — no cron mutation needed."""
        mem = _FakeMemory(baseScore=0.8, lastAccessedAt=NOW - timedelta(days=14))
        s1 = getRelevanceScore(mem, NOW)
        s2 = getRelevanceScore(mem, NOW)
        assert s1 == s2

    def test_different_times_different_scores(self):
        """Same memory at different points in time yields different scores."""
        mem = _FakeMemory(baseScore=1.0, lastAccessedAt=NOW - timedelta(days=7))
        score_now = getRelevanceScore(mem, NOW)
        score_later = getRelevanceScore(mem, NOW + timedelta(days=30))
        assert score_now > score_later
