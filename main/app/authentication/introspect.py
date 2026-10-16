import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.app.authentication.session import SessionManager
from main.app.authentication.util import verifyAccessToken
from main.models.user import User, getRolesList

logger = logging.getLogger(__name__)


def resolveSessionIdentity(db: Session, token: str) -> tuple[int, str] | None:
    try:
        payload = verifyAccessToken(token)
    except Exception:
        return None
    userIdRaw = payload.get("userId")
    sessionId = payload.get("sessionId")
    if userIdRaw is None or not sessionId:
        return None
    try:
        userId = int(userIdRaw)
    except (TypeError, ValueError):
        return None
    try:
        if not SessionManager.validateSession(db, str(sessionId), userId):
            return None
    except Exception:
        return None
    return userId, str(sessionId)


def introspectToken(db: Session, token: str | None) -> dict:
    try:
        raw = (token or "").strip().removeprefix("Bearer ").strip()
        if not raw:
            raise HTTPException(status_code=401, detail="Unauthorized")

        identity = resolveSessionIdentity(db, raw)
        if identity is None:
            raise HTTPException(status_code=401, detail="Unauthorized")

        user = db.query(User).filter(User.userId == identity[0]).first()
        if not user:
            raise HTTPException(status_code=401, detail="Unauthorized")

        return {"userId": user.userId, "username": user.username, "roles": getRolesList(user)}
    except HTTPException:
        raise HTTPException(status_code=401, detail="Unauthorized")
    except Exception as e:
        logger.warning(f"Token introspection failed: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")
