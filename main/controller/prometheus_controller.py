from config import SessionLocal
from main.utils.util import limiter, log
from main.utils.roles import Roles, Permission

from main.models.prometheus import PrometheusSession

from fastapi import APIRouter, Depends, Request, Body, HTTPException
import time

from main.app.prometheus.generation import PrometheusGenerator
from main.app.prometheus.chat import PrometheusChatManager

router = APIRouter(
    prefix="/prometheus",
    tags=["Prometheus"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "prometheus"}

@router.get("/sessions")
def getSessions(user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))):
    sessions = PrometheusChatManager.getUserSessions(user['userId'])
    return {"success": True, "sessions": sessions}

@router.post("/sessions")
def createSession(
    title: str = Body(..., embed=True), 
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))
):
    sessionId = PrometheusChatManager.createSession(user['userId'], title)
    return {"success": True, "sessionId": sessionId}

@router.put("/sessions/{sessionId}")
def updateSessionTitle(
    sessionId: str,
    title: str = Body(..., embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))
):
    if not PrometheusChatManager.verifySessionOwnership(sessionId, user['userId']):
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this session")
        
    success = PrometheusChatManager.updateSessionTitle(sessionId, title)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session title updated"}

@router.get("/history/{sessionId}")
def getHistory(sessionId: str, user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))):
    db = SessionLocal()
    try:
        session = db.query(PrometheusSession).filter(
            PrometheusSession.sessionId == sessionId,
            PrometheusSession.userId == user['userId']
        ).first()

        if not session:
            raise HTTPException(status_code=403, detail="Forbidden: You do not own this session")
            
        return {"success": True, "history": session.history or []}
    finally:
        db.close()

@router.delete("/sessions/{sessionId}")
def deleteSession(sessionId: str, user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))):
    success = PrometheusChatManager.deleteSession(sessionId, user['userId'])
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or forbidden")
    return {"success": True, "message": "Session deleted"}

@router.post("/chat")
@limiter.limit("5/minute")
def chat(
    request: Request,
    text: str = Body(..., embed=True),
    sessionId: str = Body(None, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS))
):
    try:
        if not sessionId:
            sessionId = PrometheusChatManager.createSession(user['userId'], text[:30] + "...")
        else:
            if not PrometheusChatManager.verifySessionOwnership(sessionId, user['userId']):
                raise HTTPException(status_code=403, detail="Forbidden or invalid session")

        history = PrometheusChatManager.getHistory(sessionId, limit=20)
        PrometheusChatManager.saveMessage(sessionId, "user", text)
        aiResponse = PrometheusGenerator.executeWorkflow(text, history=history, sessionId=sessionId)
        PrometheusChatManager.saveMessage(sessionId, "assistant", aiResponse)
        
        return {
            "success": True, 
            "response": aiResponse, 
            "sessionId": sessionId,
            "timestamp": str(time.time())
        }
    
    except Exception as e:
        log("error", f"Chat execution error: {str(e)}")
        return {"success": False, "error": str(e), "timestamp": str(time.time())}