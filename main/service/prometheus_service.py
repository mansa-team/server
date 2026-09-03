import logging
from config import SessionLocal
import math
from datetime import datetime

from sqlalchemy.orm import Session
from main.utils.service_manager import getApp

from main.models.memory import PrometheusMemory

from main.controller.prometheus_controller import router as prometheusRouter
from main.utils.models.loader import getEmbeddingModel

from main.utils.scheduler import registerJob

logger = logging.getLogger(__name__)

ARCHIVE_SCORE_THRESHOLD = 0.1


def memoryMaintenance(db: Session | None = None):
    ownSession = db is None
    if ownSession:
        db = SessionLocal()
    try:
        if db is None:
            logger.error("Failed to acquire DB session for memory maintenance")
            return
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
        service = getApp(port)
        service.include_router(prometheusRouter)

        getEmbeddingModel()

        registerJob(
            memoryMaintenance,
            "interval",
            jobId="memory_maintenance",
            jobName="Memory Maintenance",
            hours=24,
            jitter=600,
        )
