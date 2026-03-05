from config import SessionLocal, Config
from main.utils.util import log
from main.utils.roles import Roles
from main.models import User
from fastapi import HTTPException, Request

import jwt

SECRET_KEY = Config.USER['JWT_SECRET_KEY']
ALGORITHM = "HS256"

class UserManager:
    def __init__(self):
        pass

    def addRoleToUser(self, userId: int, role: str):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.userId == userId).first()
            
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            
            if not user.hasRole(role):
                user.addRole(role)
                db.commit()
                log("auth", f"Added role {role} to user ID {userId}")
                return True
            return False
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            log("error", f"Error adding role: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to add role")
        finally:
            db.close()

    def getCurrentUser(self, request: Request):
        token = request.cookies.get("mansa_token")
        
        if not token:
            authHeader = request.headers.get("authorization") or request.headers.get("Authorization")
            if authHeader and authHeader.startswith("Bearer "):
                token = authHeader.split(" ")[1]

        if not token:
            raise HTTPException(status_code=401, detail="Session not found")

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            userId = payload['userId']

            if userId is None:
                raise HTTPException(status_code=401, detail="Invalid Token")

            db = SessionLocal()
            try:
                user = db.query(User).filter(User.userId == userId).first()
                
                if not user:
                    raise HTTPException(status_code=401, detail="User no longer exists")
                
                return {
                    "userId": user.userId,
                    "username": user.username,
                    "email": user.email,
                    "roles": user.getRolesList()
                }
            
            finally:
                db.close()
                
        except jwt.PyJWTError:
            raise HTTPException(status_code=401, detail="Could not validate credentials")

userManager = UserManager()