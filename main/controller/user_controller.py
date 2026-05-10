import logging
from config import Config, getSession
from main.utils.logging_config import limiter
from main.app.user.user import UserManager
from sqlalchemy.orm import Session

from fastapi import APIRouter, Request, Depends, HTTPException
from main.app.authentication.session import SessionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User"])


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "user"}


@router.get("/me")
def getMe(currentUser: dict = Depends(UserManager.getCurrentUser)):
    return currentUser


@router.post("/upgrade/developer/starter")
def upgradeToDeveloperStarter(
    currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    if UserManager.addRoleToUser(db, currentUser["userId"], "DEVELOPER_STARTER"):
        return {
            "message": "Successfully upgraded to Developer Starter account",
            "roles": currentUser.get("roles", []) + ["DEVELOPER_STARTER"],
        }
    return {"message": "You are already a developer or upgrade failed"}


@router.post("/upgrade/developer/enterprise")
def upgradeToDeveloperEnterprise(
    currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    if UserManager.addRoleToUser(db, currentUser["userId"], "DEVELOPER_ENTERPRISE"):
        return {
            "message": "Successfully upgraded to Developer Enterprise account",
            "roles": currentUser.get("roles", []) + ["DEVELOPER_ENTERPRISE"],
        }
    return {"message": "You are already a developer or upgrade failed"}


@router.get("/admin")
def testAdminAccess(currentUser: dict = Depends(UserManager.getCurrentUser)):
    if "ADMIN" in currentUser.get("roles", []):
        return {"message": "Admin access granted", "user": currentUser}
    else:
        raise HTTPException(status_code=403, detail="Admin access denied")


@router.get("/sessions")
def getSessions(
    request: Request, currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    from main.app.authentication.util import verifyAccessToken

    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    currentSessionId = None
    if token:
        try:
            payload = verifyAccessToken(token)
            currentSessionId = payload.get("sessionId")
        except Exception as e:
            logger.debug(f"Token verification failed: {e}")

    sessions = SessionManager.getUserSessions(db, currentUser["userId"])
    activeCount = sum(1 for s in sessions if s.isActive)

    return {
        "sessions": [
            {
                "sessionId": s.sessionId,
                "deviceName": s.getDeviceName(),
                "browser": s.browser,
                "os": s.operatingSystem,
                "deviceType": s.deviceType,
                "lastActiveAt": s.lastActivityAt.isoformat() if s.lastActivityAt else None,
                "createdAt": s.createdAt.isoformat() if s.createdAt else None,
                "isActive": s.isActive,
                "isCurrent": s.sessionId == currentSessionId if currentSessionId else False,
            }
            for s in sessions
        ],
        "total": len(sessions),
        "active": activeCount,
    }


@router.get("/sessions/current")
def getCurrentSession(
    request: Request, currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    userAgent = request.headers.get("User-Agent", "")
    session = SessionManager.getCurrentSession(db, currentUser["userId"], userAgent, request)

    if not session:
        raise HTTPException(status_code=404, detail="Current session not found")

    return {
        "sessionId": session.sessionId,
        "deviceName": session.getDeviceName(),
        "browser": session.browser,
        "os": session.operatingSystem,
        "deviceType": session.deviceType,
        "userAgent": session.userAgent,
        "lastActiveAt": session.lastActivityAt.isoformat() if session.lastActivityAt else None,
        "createdAt": session.createdAt.isoformat() if session.createdAt else None,
    }


@router.delete("/sessions/{sessionId}")
def revokeSession(
    request: Request,
    sessionId: str,
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
):

    session = SessionManager.getSessionById(db, sessionId, currentUser["userId"])
    if not session:
        logger.warning(f"Session not found: {sessionId} for user {currentUser['userId']}")
        raise HTTPException(status_code=404, detail="Session not found")

    success = SessionManager.revokeSession(db, sessionId, currentUser["userId"])
    if not success:
        raise HTTPException(status_code=500, detail="Failed to revoke session")

    logger.info(f"Session {sessionId} revoked by user {currentUser['userId']}")
    return {"message": "Session revoked successfully", "sessionId": sessionId}


@router.post("/sessions/revoke-all")
def revokeAllSessions(
    request: Request, currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    logger.info(f"User {currentUser['userId']} requesting revoke-all for all sessions")

    revokedCount = SessionManager.revokeAllSessions(db, currentUser["userId"], exceptSessionId=None)

    logger.info(f"Revoked {revokedCount} sessions for user {currentUser['userId']}")
    return {"message": "All sessions revoked successfully", "revokedCount": revokedCount}
