import logging
from config import getSession
from main.app.user.user import UserManager
from sqlalchemy.orm import Session

from fastapi import APIRouter, Request, Depends, HTTPException, Query
from main.app.authentication.session import SessionManager
from main.app.authentication.util import extractTokenPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["User"])


@router.get("/health")
def health(request: Request):
    return {"status": "ok", "service": "user"}


@router.get("/me")
def getMe(currentUser: dict = Depends(UserManager.getCurrentUser)):
    return currentUser


@router.get("/admin")
def testAdminAccess(currentUser: dict = Depends(UserManager.getCurrentUser)):
    if "ADMIN" in currentUser.get("roles", []):
        return {"message": "Admin access granted", "user": currentUser}
    else:
        raise HTTPException(status_code=403, detail="Admin access denied")


@router.get("/sessions")
def getSessions(
    currentUser: dict = Depends(UserManager.getCurrentUser),
    db: Session = Depends(getSession),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
    payload: dict = Depends(extractTokenPayload),
):
    currentSessionId = payload.get("sessionId")

    sessions = SessionManager.getUserSessions(db, currentUser["userId"])
    activeCount = sum(1 for s in sessions if s.isActive)

    total = len(sessions)
    paginatedSessions = sessions[offset : offset + limit]

    return {
        "sessions": [
            {
                "sessionId": s.sessionId,
                "deviceName": SessionManager.getDeviceName(s),
                "browser": s.browser,
                "os": s.operatingSystem,
                "deviceType": s.deviceType,
                "lastActiveAt": s.lastActivityAt.isoformat() if s.lastActivityAt else None,
                "createdAt": s.createdAt.isoformat() if s.createdAt else None,
                "isActive": s.isActive,
                "isCurrent": s.sessionId == currentSessionId if currentSessionId else False,
            }
            for s in paginatedSessions
        ],
        "total": total,
        "active": activeCount,
        "limit": limit,
        "offset": offset,
    }


@router.get("/sessions/current")
def getCurrentSession(
    request: Request, currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)
):
    userAgent = request.headers.get("User-Agent", "")
    session = SessionManager.getCurrentSession(db, currentUser["userId"])

    if not session:
        raise HTTPException(status_code=404, detail="Current session not found")

    return {
        "sessionId": session.sessionId,
        "deviceName": SessionManager.getDeviceName(session),
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
