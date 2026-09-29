import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.app.authentication.session import SessionManager
from main.app.authentication.util import verifyAccessToken
from main.app.user.user import UserManager
from main.models.user import User

logger = logging.getLogger(__name__)

GENERIC_DETAIL = "Unauthorized"


def introspectToken(db: Session, token: str | None) -> dict:
    try:
        raw = (token or "").strip().removeprefix("Bearer ").strip()
        if not raw:
            raise HTTPException(status_code=401, detail=GENERIC_DETAIL)

        payload = verifyAccessToken(raw)

        try:
            userId = int(payload["userId"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(status_code=401, detail=GENERIC_DETAIL)

        sessionId = payload.get("sessionId")
        if not sessionId or not SessionManager.validateSession(db, str(sessionId), userId):
            raise HTTPException(status_code=401, detail=GENERIC_DETAIL)

        user = db.query(User).filter(User.userId == userId).first()
        if not user:
            raise HTTPException(status_code=401, detail=GENERIC_DETAIL)

        return {"userId": user.userId, "username": user.username, "roles": UserManager.getRolesList(user)}
    except HTTPException:
        raise HTTPException(status_code=401, detail=GENERIC_DETAIL)
    except Exception as e:
        logger.warning(f"Token introspection failed: {e}")
        raise HTTPException(status_code=401, detail=GENERIC_DETAIL)
