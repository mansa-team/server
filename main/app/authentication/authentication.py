from config import SessionLocal
from main.utils.util import log

from sqlalchemy.orm import Session
from fastapi import HTTPException

from main.app.authentication.util import *
from main.models import User

class AuthenticationManager:
    def __init__(self):
        pass

    def createUserAccount(self, username, email, password=None, googleId=None):
        if not password and not googleId:
            raise HTTPException(
                status_code=400, 
                detail="Account must have either a password."
            )
        
        db = SessionLocal()
        try:
            existingUser = db.query(User).filter(
                (User.username == username) | (User.email == email)
            ).first()
            
            if existingUser:
                if existingUser.username == username:
                    detail = "Username already taken."
                else:
                    detail = "Email already registered."
                raise HTTPException(status_code=400, detail=detail)
            
            hashedPassword = hashPassword(password) if password else None
            
            newUser = User(
                username=username,
                email=email,
                passwordHash=hashedPassword,
                googleId=googleId,
                roles=Roles.USER
            )
            
            db.add(newUser)
            db.commit()
            
            log("auth", f"User created: {username} ({email})")
            return True
            
        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            log("error", f"Error creating user: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to create user")
        finally:
            db.close()
        
    def authenticateGoogleUser(self, googleId: str):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.googleId == googleId).first()
            
            if user:
                log("auth", f"Google Login: {user.username}")
                return {
                    "userId": user.userId,
                    "username": user.username,
                    "roles": user.getRolesList()
                }
            return None
            
        finally:
            db.close()

    def authenticateUser(self, username, password):
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            
            if user and user.passwordHash and verifyPassword(password, user.passwordHash):
                log("auth", f"Password Login: {user.username}")
                return {
                    "userId": user.userId,
                    "username": user.username,
                    "roles": user.getRolesList()
                }
            return None
            
        finally:
            db.close()

authManager = AuthenticationManager()