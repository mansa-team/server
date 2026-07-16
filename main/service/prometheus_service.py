import logging

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime
from pytz import timezone

from config import SessionLocal
from main.utils.service_manager import ServiceManager
from main.controller.prometheus_controller import router as prometheusRouter
from main.utils.models.loader import getEmbeddingModel

from sqlalchemy.orm import Session
from main.models.memory import UserMemory


logger = logging.getLogger(__name__)

DECAY_FACTORS = {
    "preference": 0.99,  # sticky — decays slowly
    "analysis": 0.95,  # medium — decays normally
    "feedback": 0.97,  # medium-sticky
    "context": 0.90,  # ephemeral — decays fast
}
DEFAULT_DECAY_FACTOR = 0.95
DECAY_FACTOR = DEFAULT_DECAY_FACTOR  # backward-compat alias
ARCHIVE_SCORE_THRESHOLD = 0.1
ARCHIVE_DAYS_THRESHOLD = 90


def memoryMaintenance(db: Session | None = None):
    ownSession = db is None
    if ownSession:
        db = SessionLocal()
    try:
        assert db is not None
        nowNaive = datetime.now(timezone("America/Sao_Paulo")).replace(tzinfo=None)

        active = db.query(UserMemory).filter(UserMemory.archivedAt.is_(None)).all()
        if not active:
            return

        decayed = 0
        archived = 0

        for m in active:
            factor = DECAY_FACTORS.get(str(m.memoryType), DEFAULT_DECAY_FACTOR)
            m.baseScore = m.baseScore * factor  # type: ignore[assignment]

            lastAccessed = m.lastAccessedAt
            if lastAccessed is not None:
                if lastAccessed.tzinfo is not None:
                    lastAccessed = lastAccessed.replace(tzinfo=None)
                daysSinceAccess = (nowNaive - lastAccessed).total_seconds() / 86400
            else:
                createdNaive = m.createdAt.replace(tzinfo=None) if m.createdAt.tzinfo else m.createdAt
                daysSinceAccess = (nowNaive - createdNaive).total_seconds() / 86400

            if (
                m.baseScore < ARCHIVE_SCORE_THRESHOLD
                and m.accessCount == 0
                and daysSinceAccess > ARCHIVE_DAYS_THRESHOLD
            ):
                m.archivedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]
                archived += 1
            else:
                decayed += 1

        db.commit()
    except Exception as e:
        logger.error(f"Memory maintenance exception: {e}")
    finally:
        if ownSession and db is not None:
            db.close()


class PrometheusService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(prometheusRouter)

        getEmbeddingModel()

        scheduler = BackgroundScheduler(timezone=timezone("America/Sao_Paulo"))
        scheduler.add_job(
            memoryMaintenance,
            "interval",
            hours=24,
            timezone=timezone("America/Sao_Paulo"),
            id="memory_maintenance",
            name="Memory Maintenance",
        )
        scheduler.start()
