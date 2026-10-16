import logging
from config import SessionLocal

from main.app.authentication.csrf import CsrfProtectMiddleware
from main.app.authentication.session import SessionManager
from main.utils.service_manager import getApp
from main.utils.scheduler import registerJob
from main.controller.user_controller import router as userRouter

logger = logging.getLogger(__name__)


def removeInactiveSessions():
    db = SessionLocal()
    try:
        SessionManager.purgeInactive(db)
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting the user_session: {str(e)}", exc_info=True)
    finally:
        db.close()


class UserService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port, middleware=[CsrfProtectMiddleware])
        service.include_router(userRouter)

        registerJob(
            removeInactiveSessions,
            "interval",
            jobId="cleanup_inactive_sessions",
            jobName="Remove inactive sessions",
            hours=12,
        )
