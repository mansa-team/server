import logging
import math

from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime

from config import SessionLocal
from main.utils.service_manager import ServiceManager
from main.controller.prometheus_controller import router as prometheusRouter
from main.utils.models.loader import getEmbeddingModel

from sqlalchemy.orm import Session
from main.models.memory import PrometheusMemory


logger = logging.getLogger(__name__)

ARCHIVE_SCORE_THRESHOLD = 0.1


def memoryMaintenance(db: Session | None = None):
    ownSession = db is None
    if ownSession:
        db = SessionLocal()
    try:
        assert db is not None
        nowNaive = datetime.now().replace(tzinfo=None)

        active = db.query(PrometheusMemory).filter(PrometheusMemory.archivedAt.is_(None)).all()
        if not active:
            return

        archived = 0

        for m in active:
            if m.lastAccessedAt is not None:
                lastAccessed = m.lastAccessedAt.replace(tzinfo=None) if m.lastAccessedAt.tzinfo else m.lastAccessedAt
                daysSinceAccess = (nowNaive - lastAccessed).total_seconds() / 86400
            else:
                createdNaive = m.createdAt.replace(tzinfo=None) if m.createdAt.tzinfo else m.createdAt
                daysSinceAccess = (nowNaive - createdNaive).total_seconds() / 86400

            stability = max(m.score, 0.1)
            retention = math.exp(-daysSinceAccess / stability)

            if retention < ARCHIVE_SCORE_THRESHOLD and m.accessCount == 0:
                m.archivedAt = datetime.now()  # type: ignore[assignment]
                archived += 1

        db.commit()
        if archived:
            logger.info(f"Archived {archived} dead memories")
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

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            memoryMaintenance,
            "interval",
            hours=24,
            id="memory_maintenance",
            name="Memory Maintenance",
        )
        scheduler.start()
