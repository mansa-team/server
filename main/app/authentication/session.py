import logging
import secrets
from datetime import datetime, timedelta, timezone
import hashlib
from sqlalchemy.orm import Session
from user_agents import parse as parseUserAgent
from main.models.user_session import UserSession
from main.app.authentication.constants import SESSION_EXPIRY_DAYS

logger = logging.getLogger(__name__)


def parseDeviceFields(userAgent: str | None) -> tuple[str | None, str | None, str | None]:
    if not userAgent:
        return None, None, None
    parsed = parseUserAgent(userAgent)
    if parsed.is_tablet:
        deviceType: str | None = "tablet"
    elif parsed.is_mobile:
        deviceType = "mobile"
    elif parsed.is_pc:
        deviceType = "desktop"
    else:
        deviceType = None
    browser = parsed.browser.family if parsed.browser.family != "Other" else None
    operatingSystem = parsed.os.family if parsed.os.family != "Other" else None
    return deviceType, browser, operatingSystem


class SessionManager:
    @staticmethod
    def createSession(
        db: Session,
        userId: int,
        userAgent: str | None,
        expiresAt: datetime | None = None,
    ) -> UserSession:
        sessionId = secrets.token_urlsafe(32)
        accessTokenHash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()[:64]

        now = datetime.now(timezone.utc)
        if expiresAt is None:
            expiresAt = now + timedelta(days=SESSION_EXPIRY_DAYS)

        deviceType, browser, operatingSystem = parseDeviceFields(userAgent)

        session = UserSession(
            sessionId=sessionId,
            userId=userId,
            accessTokenHash=accessTokenHash,
            deviceType=deviceType,
            browser=browser,
            operatingSystem=operatingSystem,
            userAgent=userAgent,
            isActive=True,
            createdAt=now,
            lastActivityAt=now,
            expiresAt=expiresAt,
        )

        db.add(session)
        db.commit()

        logger.info(f"Created session {sessionId} for user {userId}")
        return session

    @staticmethod
    def getUserSessions(db: Session, userId: int, limit: int = 50) -> list[UserSession]:
        query = db.query(UserSession).filter(UserSession.userId == userId, UserSession.isActive)
        return query.order_by(UserSession.lastActivityAt.desc()).limit(limit).all()

    @staticmethod
    def getSessionById(db: Session, sessionId: str, userId: int | None = None) -> UserSession | None:
        query = db.query(UserSession).filter(UserSession.sessionId == str(sessionId))
        if userId:
            query = query.filter(UserSession.userId == userId)
        return query.first()

    @staticmethod
    def getCurrentSession(db: Session, userId: int) -> UserSession | None:
        return (
            db.query(UserSession)
            .filter(
                UserSession.userId == userId,
                UserSession.isActive,
            )
            .order_by(UserSession.lastActivityAt.desc())
            .first()
        )

    @staticmethod
    def revokeSession(db: Session, sessionId: str, userId: int) -> bool:
        session = SessionManager.getSessionById(db, sessionId, userId)
        if not session:
            return False

        session.isActive = False  # type: ignore[assignment]
        db.commit()

        logger.info(f"Revoked session {sessionId} for user {userId}")
        return True

    @staticmethod
    def revokeAllSessions(db: Session, userId: int) -> int:
        query = db.query(UserSession).filter(
            UserSession.userId == userId,
            UserSession.isActive,
        )

        count = query.update({UserSession.isActive: False}, synchronize_session=False)
        db.commit()

        logger.info(f"Revoked {count} sessions for user {userId}")
        return count

    @staticmethod
    def updateLastActive(db: Session, sessionId: str) -> bool:
        session = db.query(UserSession).filter(UserSession.sessionId == sessionId).first()
        if not session:
            return False

        session.lastActivityAt = datetime.now(timezone.utc)  # type: ignore[assignment]
        db.commit()
        return True

    @staticmethod
    def validateSession(db: Session, sessionId: str, userId: int) -> bool:
        session = SessionManager.getSessionById(db, sessionId, userId)
        if not session:
            return False

        if not session.isActive:
            return False

        if session.expiresAt:
            expTime = session.expiresAt
            if expTime.tzinfo is None:
                expTime = expTime.replace(tzinfo=timezone.utc)
            if expTime < datetime.now(timezone.utc):
                session.isActive = False  # type: ignore[assignment]
                db.commit()
                return False

        return True
