import pytest
from datetime import datetime, timedelta
from pytz import timezone

from main.service.prometheus_service import memoryMaintenance, DECAY_FACTORS, DEFAULT_DECAY_FACTOR
from main.models.memory import PrometheusMemory

BRT = timezone("America/Sao_Paulo")


def _create(dbSession, userId, key, memoryType, baseScore=1.0, daysOld=30):
    now = datetime.now(BRT)
    lastAccessed = now - timedelta(days=daysOld)
    mem = PrometheusMemory(
        userId=userId,
        memoryKey=key,
        memoryValue=f"value_{key}",
        memoryType=memoryType,
        source="inferred",
        baseScore=baseScore,
        accessCount=5,
        lastAccessedAt=lastAccessed,
    )
    dbSession.add(mem)
    dbSession.commit()
    return mem


class TestTypeAwareDecay:
    def test_preference_decays_slowly(self, dbSession):
        mem = _create(dbSession, 1, "pref1", "preference", baseScore=1.0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(1.0 * DECAY_FACTORS["preference"], abs=1e-6)

    def test_context_decays_fast(self, dbSession):
        mem = _create(dbSession, 1, "ctx1", "context", baseScore=1.0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(1.0 * DECAY_FACTORS["context"], abs=1e-6)

    def test_analysis_decays_normally(self, dbSession):
        mem = _create(dbSession, 1, "ana1", "analysis", baseScore=1.0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(1.0 * DECAY_FACTORS["analysis"], abs=1e-6)

    def test_feedback_decays_medium(self, dbSession):
        mem = _create(dbSession, 1, "fb1", "feedback", baseScore=1.0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(1.0 * DECAY_FACTORS["feedback"], abs=1e-6)

    def test_unknown_type_uses_default(self, dbSession):
        mem = _create(dbSession, 1, "unk1", "unknown_type", baseScore=1.0)
        memoryMaintenance(dbSession)
        dbSession.refresh(mem)
        assert mem.baseScore == pytest.approx(1.0 * DEFAULT_DECAY_FACTOR, abs=1e-6)

    def test_mixed_types_all_correct(self, dbSession):
        prefs = _create(dbSession, 1, "p1", "preference", baseScore=1.0)
        ctx = _create(dbSession, 2, "c1", "context", baseScore=1.0)
        ana = _create(dbSession, 3, "a1", "analysis", baseScore=1.0)
        fb = _create(dbSession, 4, "f1", "feedback", baseScore=1.0)

        memoryMaintenance(dbSession)

        for mem in [prefs, ctx, ana, fb]:
            dbSession.refresh(mem)

        assert prefs.baseScore == pytest.approx(1.0 * 0.99, abs=1e-6)
        assert ctx.baseScore == pytest.approx(1.0 * 0.90, abs=1e-6)
        assert ana.baseScore == pytest.approx(1.0 * 0.95, abs=1e-6)
        assert fb.baseScore == pytest.approx(1.0 * 0.97, abs=1e-6)

    def test_preference_survives_longer(self, dbSession):
        """After 10 cycles, preference (0.99^10) > context (0.90^10)."""
        pref = _create(dbSession, 1, "pref_long", "preference", baseScore=0.5)
        ctx = _create(dbSession, 2, "ctx_long", "context", baseScore=0.5)

        for _ in range(10):
            memoryMaintenance(dbSession)
            dbSession.refresh(pref)
            dbSession.refresh(ctx)

        assert pref.baseScore > ctx.baseScore
        assert pref.baseScore == pytest.approx(0.5 * (0.99**10), abs=1e-6)
        assert ctx.baseScore == pytest.approx(0.5 * (0.90**10), abs=1e-6)
