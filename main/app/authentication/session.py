import logging
import secrets
from datetime import datetime, timedelta, timezone
import hashlib
from sqlalchemy.orm import Session
from main.models.user_session import UserSession
from main.app.authentication.constants import SESSION_EXPIRY_DAYS

logger = logging.getLogger(__name__)


class SessionManager:
    @staticmethod
    def getDeviceName(session) -> str:
        if session.browser and session.operatingSystem:
            return f"{session.browser} on {session.operatingSystem}"
        elif session.accessTokenHash:
            return f"Device {session.accessTokenHash[:8]}"
        return "Unknown Device"

    @staticmethod
    def createSession(
        db: Session,
        userId: int,
        userAgent: str,
        expiresAt: datetime | None = None,
    ) -> UserSession:
        sessionId = secrets.token_urlsafe(32)
        accessTokenHash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()[:64]

        now = datetime.now(timezone.utc)
        if expiresAt is None:
            expiresAt = now + timedelta(days=SESSION_EXPIRY_DAYS)

        session = UserSession(
            sessionId=sessionId,
            userId=userId,
            accessTokenHash=accessTokenHash,
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
    def getUserSessions(db: Session, userId: int, includeInactive: bool = False, limit: int = 50) -> list[UserSession]:
        query = db.query(UserSession).filter(UserSession.userId == userId)
        if not includeInactive:
            query = query.filter(UserSession.isActive)
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
    def revokeAllSessions(db: Session, userId: int, exceptSessionId: str | None = None) -> int:
        query = db.query(UserSession).filter(
            UserSession.userId == userId,
            UserSession.isActive,
        )

        if exceptSessionId:
            query = query.filter(UserSession.sessionId != exceptSessionId)

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
