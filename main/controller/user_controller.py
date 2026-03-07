from config import Config, getSession
from main.utils.util import log, limiter
from main.app.user.user import userManager
from main.utils.roles import Roles
from sqlalchemy.orm import Session

from fastapi import APIRouter, Request, Depends

router = APIRouter(
    prefix="/user",
    tags=["User"]
)

@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "user"}

@router.get("/me")
def getMe(currentUser: dict = Depends(userManager.getCurrentUser)):
    return currentUser

@router.post("/upgrade/developer")
def upgradeToDeveloper(currentUser: dict = Depends(userManager.getCurrentUser), db: Session = Depends(getSession)):
    if userManager.addRoleToUser(db, currentUser['userId'], Roles.DEVELOPER):
        return {"message": "Successfully upgraded to Developer account", "roles": currentUser.get('roles', []) + [Roles.DEVELOPER]}
    return {"message": "You are already a developer or upgrade failed"}