import secrets
from datetime import datetime, timedelta, timezone
import hashlib
from sqlalchemy.orm import Session
from main.models.user_session import UserSession
from main.app.authentication.device import parseUserAgent
from main.utils.util import log

class SessionManager:
    @staticmethod
    def createSession(
        db: Session,
        userId: int,
        userAgent: str,
        request,
        expiresAt: datetime = None,
    ) -> UserSession:
        sessionId = secrets.token_urlsafe(32)
        accessTokenHash = hashlib.sha256(secrets.token_hex(32).encode()).hexdigest()[:64]

        deviceInfo = parseUserAgent(userAgent)

        now = datetime.now(timezone.utc)
        if expiresAt is None:
            expiresAt = now + timedelta(hours=24)

        session = UserSession(
            sessionId=sessionId,
            userId=userId,
            accessTokenHash=accessTokenHash,
            deviceType=deviceInfo.deviceType,
            browser=deviceInfo.browser,
            operatingSystem=deviceInfo.os,
            userAgent=userAgent,
            isActive=True,
            createdAt=now,
            lastActivityAt=now,
            expiresAt=expiresAt,
        )

        db.add(session)
        db.commit()

        log("session", f"Created session {sessionId} for user {userId}")
        return session

    @staticmethod
    def getUserSessions(db: Session, userId: int, includeInactive: bool = False, limit: int = 50) -> list[UserSession]:
        query = db.query(UserSession).filter(UserSession.userId == userId)
        if not includeInactive:
            query = query.filter(UserSession.isActive)
        return query.order_by(UserSession.lastActivityAt.desc()).limit(limit).all()

    @staticmethod
    def getSessionById(db: Session, sessionId: str, userId: int = None) -> UserSession | None:
        query = db.query(UserSession).filter(UserSession.sessionId == str(sessionId))
        if userId:
            query = query.filter(UserSession.userId == userId)
        return query.first()

    @staticmethod
    def getSessionByIdSafe(db: Session, sessionId: str) -> UserSession | None:
        return db.query(UserSession).filter(UserSession.sessionId == str(sessionId)).first()

    @staticmethod
    def getCurrentSession(db: Session, userId: int, userAgent: str, request) -> UserSession | None:
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

        session.isActive = False
        db.commit()

        log("session", f"Revoked session {sessionId} for user {userId}")
        return True

    @staticmethod
    def revokeAllSessions(db: Session, userId: int, exceptSessionId: str = None) -> int:
        query = db.query(UserSession).filter(
            UserSession.userId == userId,
            UserSession.isActive,
        )

        if exceptSessionId:
            query = query.filter(UserSession.sessionId != exceptSessionId)

        count = query.update({UserSession.isActive: False}, synchronize_session=False)
        db.commit()

        log("session", f"Revoked {count} sessions for user {userId}")
        return count

    @staticmethod
    def updateLastActive(db: Session, sessionId: str) -> bool:
        session = db.query(UserSession).filter(UserSession.sessionId == sessionId).first()
        if not session:
            return False

        session.lastActivityAt = datetime.now(timezone.utc)
        db.commit()
        return True

    @staticmethod
    def cleanupExpiredSessions(db: Session) -> int:
        now = datetime.now(timezone.utc)
        count = db.query(UserSession).filter(
            UserSession.isActive,
            UserSession.expiresAt < now,
        ).update({UserSession.isActive: False}, synchronize_session=False)
        db.commit()

        if count > 0:
            log("session", f"Cleaned up {count} expired sessions")

        return count

    @staticmethod
    def validateSession(db: Session, sessionId: str, userId: int) -> bool:
        session = SessionManager.getSessionById(db, sessionId, userId)
        if not session:
            return False

        if not session.isActive:
            return False

        if session.expiresAt and session.expiresAt < datetime.now(timezone.utc):
            session.isActive = False
            db.commit()
            return False

        return True