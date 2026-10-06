import logging
from config import getSession

from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session

from main.models.user import User

from main.app.authentication.session import SessionManager, detectSessionAnomaly
from main.app.authentication.util import extractTokenPayload, getClientIp

logger = logging.getLogger(__name__)


class UserManager:
    @staticmethod
    def getRolesList(user: User) -> list[str]:
        if not user.roles:
            return ["USER"]
        return [role.strip() for role in user.roles.split(",")]

    @staticmethod
    def getCurrentUser(
        request: Request,
        payload: dict = Depends(extractTokenPayload),
        db: Session = Depends(getSession),
    ):
        try:
            userId = payload.get("userId")
            sessionId = payload.get("sessionId")

            if not sessionId or userId is None:
                logger.info("Missing sessionId in token, rejecting")
                raise HTTPException(status_code=401, detail="Session required")

            currentUa = request.headers.get("User-Agent") if request is not None else None
            currentIp = getClientIp(request) if request is not None else None
            isValid = SessionManager.validateSession(db, sessionId, int(userId), currentUa, currentIp)
            if not isValid:
                logger.info(f"Session {sessionId} revoked, logging out user {userId}")
                raise HTTPException(status_code=401, detail="Session revoked")

            user = db.query(User).filter(User.userId == userId).first()

            if not user:
                raise HTTPException(status_code=401, detail="User no longer exists")

            # Flag-only anomaly: surfaced, never rejects.
            try:
                session = SessionManager.getSessionById(db, str(sessionId), int(userId))
                anomaly = (
                    detectSessionAnomaly(session, currentUa, currentIp)
                    if session is not None
                    else {"userAgentChanged": False, "subnet": None}
                )
            except Exception:
                anomaly = {"userAgentChanged": False, "subnet": None}

            result = {
                "userId": user.userId,
                "username": user.username,
                "email": user.email,
                "roles": UserManager.getRolesList(user),
                "sessionId": sessionId,
                "sessionAnomaly": anomaly,
            }

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in getCurrentUser: {str(e)}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not validate credentials")
