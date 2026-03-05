from config import SessionLocal
from main.utils.util import log
from main.utils.roles import Roles
from main.models import User
from fastapi import HTTPException

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

userManager = UserManager()