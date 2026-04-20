from config import getSession
from main.utils.util import log
from main.models import User
from fastapi import HTTPException, Request, Depends
from sqlalchemy.orm import Session

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
            log("auth", f"Added role {role} to user {userId}")
            return True
        return False

    @staticmethod
    def getCurrentUser(request: Request, db: Session = Depends(getSession)):
        from main.app.authentication.util import verifyAccessToken

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

            if userId is None:
                raise HTTPException(status_code=401, detail="Invalid Token")

            user = db.query(User).filter(User.userId == userId).first()

            if not user:
                raise HTTPException(status_code=401, detail="User no longer exists")

            return {
                "userId": user.userId,
                "username": user.username,
                "email": user.email,
                "roles": user.getRolesList(),
            }

        except HTTPException:
            raise
        except Exception as e:
            log("error", f"Error in getCurrentUser: {str(e)}")
            raise HTTPException(status_code=401, detail="Could not validate credentials")