import logging
from config import getSession

from fastapi import HTTPException, Depends, Request
from sqlalchemy.orm import Session

from main.models.user import User, getRolesList

from main.app.authentication.session import SessionManager
from main.app.authentication.util import extractTokenPayload
from main.utils.roles import Permission, Roles

logger = logging.getLogger(__name__)


class UserManager:
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
                "roles": getRolesList(user),
                "sessionId": sessionId,
            }

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in getCurrentUser: {str(e)}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not validate credentials")


def requirePermission(perm: Permission):
    async def checker(user: dict = Depends(UserManager.getCurrentUser)):
        if not Roles.checkAccess(user.get("roles", []), perm):
            raise HTTPException(status_code=403, detail=f"Missing required permission: {perm.name}")
        return user

    return checker
