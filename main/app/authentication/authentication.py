import logging
from main.utils.roles import Roles

from sqlalchemy.orm import Session
from fastapi import HTTPException

from main.app.authentication.util import hashPassword, verifyPassword
from main.app.user.user import UserManager
from main.models import User

logger = logging.getLogger(__name__)


class AuthenticationManager:
    @staticmethod
    def createUserAccount(db: Session, username, email, password=None, googleId=None):
        if not password and not googleId:
            raise HTTPException(status_code=400, detail="Account must have either a password.")

        try:
            existingUser = db.query(User).filter((User.username == username) | (User.email == email)).first()

            if existingUser:
                if existingUser.username == username:
                    detail = "Username already taken."
                else:
                    detail = "Email already registered."
                raise HTTPException(status_code=400, detail=detail)

            hashedPassword = hashPassword(password) if password else None

            newUser = User(
                username=username, email=email, passwordHash=hashedPassword, googleId=googleId, roles=Roles.USER.name
            )

            db.add(newUser)
            db.commit()

            logger.info(f"User created: {username} ({email})")
            return True

        except HTTPException:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating user: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create user")

    @staticmethod
    def authenticateGoogleUser(db: Session, googleId: str):
        try:
            user = db.query(User).filter(User.googleId == googleId).first()

            if user:
                logger.info(f"Google Login: {user.username}")
                return {"userId": user.userId, "username": user.username, "roles": UserManager.getRolesList(user)}
            return None

        except Exception as e:
            logger.debug(f"Error authenticating Google user: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def authenticateUser(db: Session, username, password):
        try:
            user = db.query(User).filter(User.username == username).first()

            if user and user.passwordHash and verifyPassword(password, str(user.passwordHash)):
                logger.info(f"Password Login: {user.username}")
                return {"userId": user.userId, "username": user.username, "roles": UserManager.getRolesList(user)}
            return None

        except Exception as e:
            logger.debug(f"Error authenticating user: {str(e)}", exc_info=True)
            return None
