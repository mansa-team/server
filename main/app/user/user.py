import logging
from config import getSession
from main.models import User
from fastapi import HTTPException, Request, Depends
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class UserManager:
    def __init__(self):
        pass

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
    def getCurrentUser(request: Request, db: Session = Depends(getSession)):
        from main.app.authentication.util import verifyAccessToken
        from main.app.authentication.session import SessionManager

        token = request.headers.get("X-Access-Token")
        if not token:
            authHeader = request.headers.get("Authorization")
            if authHeader and authHeader.startswith("Bearer "):
                token = authHeader.split(" ")[1]

        if not token:
            raise HTTPException(status_code=401, detail="Session not found")

        try:
            payload = verifyAccessToken(token)
            userId = payload.get("userId")
            sessionId = payload.get("sessionId")

            if userId is None:
                raise HTTPException(status_code=401, detail="Invalid Token")

            if sessionId:
                isValid = SessionManager.validateSession(db, sessionId, userId)
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
                try:
                    result["sessionId"] = sessionId
                except (ValueError, TypeError):
                    pass

            return result

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error in getCurrentUser: {str(e)}", exc_info=True)
            raise HTTPException(status_code=401, detail="Could not validate credentials")
