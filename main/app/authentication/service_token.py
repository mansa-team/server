"""Service loopback tokens: opaque session rows, minted per-request.

A token is a UserSession.sessionId row owned by the internal service user,
created via SessionManager and verified with a single ownership-checked read.
Rotation without restart is SessionManager.revokeSession (or expiry).
Replaces the retired JWT/HMAC dual-path: no crypto here, no import-time mint.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from config import Config
from main.app.authentication.session import SessionManager
from main.models.user import User

logger = logging.getLogger(__name__)

SERVICE_USERNAME = "service-loopback"


def getServiceUserId(db: Session) -> int:
    user = db.query(User).filter(User.username == SERVICE_USERNAME).first()
    if user is None:
        user = User(
            username=SERVICE_USERNAME,
            email="service-loopback@internal",
            passwordHash=None,
            roles="SERVICE",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return int(user.userId)


def createServiceToken(db: Session, expiresDelta: timedelta | None = None) -> str:
    if expiresDelta is None:
        expiresDelta = timedelta(hours=Config.USER.SERVICE_TOKEN_TTL_HOURS)
    serviceId = getServiceUserId(db)
    session = SessionManager.createSession(db, serviceId, "service-loopback", datetime.now(timezone.utc) + expiresDelta)
    return str(session.sessionId)


def verifyServiceToken(db: Session, provided: str | None) -> bool:
    token = (provided or "").strip()
    if not token:
        return False
    try:
        session = SessionManager.getSessionById(db, token)
        service = db.query(User).filter(User.username == SERVICE_USERNAME).first()
    except Exception:
        return False
    if session is None or not session.isActive:
        return False
    if service is None or int(session.userId) != int(service.userId):
        return False
    expiresAt = session.expiresAt
    if expiresAt is not None:
        if expiresAt.tzinfo is None:
            expiresAt = expiresAt.replace(tzinfo=timezone.utc)
        if expiresAt < datetime.now(timezone.utc):
            session.isActive = False  # type: ignore[assignment]
            db.commit()
            return False
    return True
