import logging
from config import SessionLocal

from datetime import datetime, timedelta, timezone
from sqlalchemy import or_

from main.models.user_session import UserSession

from main.app.authentication.constants import SESSION_EXPIRY_DAYS
from main.utils.service_manager import getApp
from main.controller.user_controller import router as userRouter

logger = logging.getLogger(__name__)


def removeInactiveSessions():
    db = SessionLocal()
    try:
        # M2: also purge expired-but-still-active rows (validateSession only
        # lazily deactivates on next touch, so these accumulated forever).
        # Expired active: isActive & expiresAt < now. Long-dead inactive:
        # ~isActive & lastActivityAt < now - 30d. Uses the composite index
        # ix_user_sessions_active_lastactive on (isActive, lastActivityAt).
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


def registerSessionCleanupJobs():
    """P5: register the session-cleanup job on the shared scheduler.

    Kept in this service file so per-service management grouping is
    preserved — only the scheduler *instance* is shared. Same 12h cadence
    and stable job id as before; jitter staggers it off other jobs.
    """
    from main.utils.scheduler import registerJob

    registerJob(
        removeInactiveSessions,
        "interval",
        jobId="cleanup_inactive_sessions",
        jobName="Remove inactive sessions",
        hours=12,
        jitter=300,
    )
    logger.info("Session cleanup scheduled on shared scheduler (every 12h)")


class UserService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(userRouter)

        registerSessionCleanupJobs()
