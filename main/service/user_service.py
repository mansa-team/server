import logging
import time
from datetime import datetime, timedelta
from pytz import timezone
import threading

from config import SessionLocal
from main.models.user_session import UserSession
from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from main.utils.service_manager import ServiceManager
from main.controller.user_controller import router as userRouter

logger = logging.getLogger(__name__)


def removeInactiveSessions():
    db = SessionLocal()
    try:
        thresholdDate = datetime.now(timezone("America/Sao_Paulo")) - timedelta(days=SESSION_EXPIRY_DAYS)

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


def inactiveSessionsScheduler():
    def scheduler():
        while True:
            try:
                time.sleep(12 * 60 * 60)  # 12 hours
                removeInactiveSessions()
            except Exception as e:
                logger.error(f"Session cleanup scheduler error: {str(e)}", exc_info=True)
                time.sleep(60)

    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()


class UserService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(userRouter)

    inactiveSessionsScheduler()
