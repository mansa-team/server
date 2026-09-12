import logging
from config import getSession

from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session

from main.models.user import User

from main.app.authentication.util import extractTokenPayload

logger = logging.getLogger(__name__)


class UserManager:
    @staticmethod
    def getRolesList(user: User) -> list[str]:
        if not user.roles:
            return ["USER"]
        return [role.strip() for role in user.roles.split(",")]

    @staticmethod
    def getCurrentUser(
        payload: dict = Depends(extractTokenPayload),
        db: Session = Depends(getSession),
    ):
        from main.app.authentication.session import SessionManager

        try:
            userId = payload.get("userId")
            sessionId = payload.get("sessionId")

            if sessionId and userId is not None:
                isValid = SessionManager.validateSession(db, sessionId, int(userId))
                if not isValid:
                    logger.info(f"Session {sessionId} revoked, logging out user {userId}")
                    raise HTTPException(status_code=401, detail="Session revoked")

            user = db.query(User).filter(User.userId == userId).first()

            if not user:
                raise HTTPException(status_code=401, detail="User no longer exists")

            result = {
                "userId": user.userId,
                "username": user.username,
                "email": user.email,
                "roles": UserManager.getRolesList(user),
            }

            if sessionId:
                result["sessionId"] = sessionId

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in getCurrentUser: {str(e)}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not validate credentials")
