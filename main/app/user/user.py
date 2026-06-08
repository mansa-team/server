import logging
from config import getSession
from main.models import User
from fastapi import HTTPException, Depends
from sqlalchemy.orm import Session
from main.app.authentication.util import extractTokenPayload

logger = logging.getLogger(__name__)


class UserManager:
    @staticmethod
    def addRoleToUser(db: Session, userId: int, role: str):
        user = db.query(User).filter(User.userId == userId).first()

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.hasRole(role):
            user.addRole(role)
            db.commit()
            logger.info(f"Added role {role} to user {userId}")
            return True
        return False

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
                "roles": user.getRolesList(),
            }

            if sessionId:
                result["sessionId"] = sessionId

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in getCurrentUser: {str(e)}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not validate credentials")
