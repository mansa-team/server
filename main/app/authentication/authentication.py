from main.utils.util import log

from sqlalchemy.orm import Session
from fastapi import HTTPException

from main.app.authentication.util import *
from main.models import User

class AuthenticationManager:
    def __init__(self):
        pass

    def createUserAccount(self, db: Session, username, email, password=None, googleId=None):
        if not password and not googleId:
            raise HTTPException(
                status_code=400, 
                detail="Account must have either a password."
            )
        
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
                roles=Roles.USER.name
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
        
    def authenticateGoogleUser(self, db: Session, googleId: str):
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
            
        except Exception as e:
            log("error", f"Error authenticating Google user: {str(e)}")
            return None

    def authenticateUser(self, db: Session, username, password):
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
            
        except Exception as e:
            log("error", f"Error authenticating user: {str(e)}")
            return None

authManager = AuthenticationManager()