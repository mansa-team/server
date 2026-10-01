import logging
from config import SessionLocal

from datetime import datetime, timedelta, timezone
from sqlalchemy import or_

from main.models.user_session import UserSession

from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from main.utils.service_manager import getApp
from main.utils.scheduler import registerJob
from main.controller.user_controller import router as userRouter

logger = logging.getLogger(__name__)


def removeInactiveSessions():
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        thresholdDate = now - timedelta(days=SESSION_EXPIRY_DAYS)

        deleted = (
            db.query(UserSession)
            .filter(
                or_(
                    (UserSession.isActive & (UserSession.expiresAt < now)),
                    (~UserSession.isActive & (UserSession.lastActivityAt < thresholdDate)),
                )
            )
            .delete(synchronize_session=False)
        )
        db.commit()
        logger.info(f"Removed {deleted} inactive sessions")
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting the user_session: {str(e)}", exc_info=True)
    finally:
        db.close()


class UserService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(userRouter)

        registerJob(
            removeInactiveSessions,
            "interval",
            jobId="cleanup_inactive_sessions",
            jobName="Remove inactive sessions",
            hours=12,
        )
