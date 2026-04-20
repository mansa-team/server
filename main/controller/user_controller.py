from config import Config, getSession
from main.utils.util import log, limiter
from main.app.user.user import UserManager
from main.utils.roles import Roles
from sqlalchemy.orm import Session

from fastapi import APIRouter, Request, Depends

router = APIRouter(prefix="/user", tags=["User"])

@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "user"}

@router.get("/me")
def getMe(currentUser: dict = Depends(UserManager.getCurrentUser)):
    return currentUser

@router.post("/upgrade/developer/starter")
def upgradeToDeveloperStarter(currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)):
    if UserManager.addRoleToUser(db, currentUser['userId'], "DEVELOPER_STARTER"):
        return {"message": "Successfully upgraded to Developer Starter account", "roles": currentUser.get('roles', []) + ["DEVELOPER_STARTER"]}
    return {"message": "You are already a developer or upgrade failed"}

@router.post("/upgrade/developer/enterprise")
def upgradeToDeveloperEnterprise(currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)):
    if UserManager.addRoleToUser(db, currentUser['userId'], "DEVELOPER_ENTERPRISE"):
        return {"message": "Successfully upgraded to Developer Enterprise account", "roles": currentUser.get('roles', []) + ["DEVELOPER_ENTERPRISE"]}
    return {"message": "You are already a developer or upgrade failed"}

@router.get("/admin")
def testAdminAccess(currentUser: dict = Depends(UserManager.getCurrentUser)):
    if "ADMIN" in currentUser.get('roles', []):
        return {"message": "Admin access granted", "user": currentUser}
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access denied")