from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.app.authentication.session import SessionManager
from main.app.authentication.util import verifyAccessToken
from main.app.user.user import UserManager
from main.models.user import User


def introspectToken(db: Session, token: str | None) -> dict:
    raw = (token or "").strip().removeprefix("Bearer ").strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Token not provided")

    payload = verifyAccessToken(raw)

    try:
        userId = int(payload["userId"])
    except (KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token")

    sessionId = payload.get("sessionId")
    if not sessionId or not SessionManager.validateSession(db, str(sessionId), userId):
        raise HTTPException(status_code=401, detail="Session revoked")

    user = db.query(User).filter(User.userId == userId).first()
    if not user:
        raise HTTPException(status_code=401, detail="User no longer exists")

    return {"userId": user.userId, "username": user.username, "roles": UserManager.getRolesList(user)}
