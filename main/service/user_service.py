import logging
from config import SessionLocal

from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

from main.models.user_session import UserSession

from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from main.utils.service_manager import ServiceManager
from main.controller.user_controller import router as userRouter

logger = logging.getLogger(__name__)


def removeInactiveSessions():
    db = SessionLocal()
    try:
        thresholdDate = datetime.now() - timedelta(days=SESSION_EXPIRY_DAYS)

        deleted = (
            db.query(UserSession)
            .filter(~UserSession.isActive, UserSession.lastActivityAt < thresholdDate)
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(f"Removed {deleted} inactive sessions")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting the user_session: {str(e)}", exc_info=True)
    finally:
        db.close()


scheduler = None


class UserService:
    @staticmethod
    def initialize(port: int):
        global scheduler
        service = ServiceManager.getApp(port)
        service.include_router(userRouter)

        scheduler = BackgroundScheduler()
        scheduler.add_job(
            removeInactiveSessions,
            "interval",
            hours=12,
            id="cleanup_inactive_sessions",
            name="Remove inactive sessions",
        )
        scheduler.start()
        logger.info("Session cleanup scheduler started (every 12h)")
