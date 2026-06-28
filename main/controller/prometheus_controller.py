import json
import logging
import asyncio
from config import getSession
from main.utils.logging_config import limiter
from main.utils.roles import Roles, Permission

from sqlalchemy.orm import Session
from main.models.prometheus import PrometheusSession

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import StreamingResponse
import time

from main.app.prometheus.agent import Prometheus
from main.app.prometheus.chat import PrometheusChatManager
from fastapi import Body

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prometheus", tags=["Prometheus"])


def verifySessionOwnsership(db: Session, sessionId: str, userId: int):
    if not PrometheusChatManager.verifySessionOwnership(db, sessionId, userId):
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this session")


@router.get("/health")
def health():
    return {"status": "ok", "service": "prometheus"}


@router.get("/sessions")
def getSessions(
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
):
    sessions = PrometheusChatManager.getUserSessions(db, user["userId"])
    total = len(sessions)
    paginatedSessions = sessions[offset : offset + limit]
    return {
        "success": True,
        "sessions": paginatedSessions,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/sessions")
def createSession(
    db: Session = Depends(getSession),
    title: str = Body(..., min_length=1, max_length=200, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    sessionId = PrometheusChatManager.createSession(db, user["userId"], title)
    return {"success": True, "sessionId": sessionId}


@router.put("/sessions/{sessionId}")
def updateSessionTitle(
    sessionId: str,
    db: Session = Depends(getSession),
    title: str = Body(..., min_length=1, max_length=200, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])

    success = PrometheusChatManager.updateSessionTitle(db, sessionId, title)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session title updated"}


@router.get("/history/{sessionId}")
def getHistory(
    sessionId: str,
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])
    session = (
        db.query(PrometheusSession)
        .filter(PrometheusSession.sessionId == sessionId, PrometheusSession.userId == user["userId"])
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "history": session.history or []}


@router.delete("/sessions/{sessionId}")
def deleteSession(
    sessionId: str,
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    success = PrometheusChatManager.deleteSession(db, sessionId, user["userId"])
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or forbidden")
    return {"success": True, "message": "Session deleted"}


@router.post("/chat")
@limiter.limit("5/minute")
async def chat(
    request: Request,
    db: Session = Depends(getSession),
    query: str = Body(..., min_length=1, max_length=10000, embed=True),
    sessionId: str = Body(default=None, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    if not sessionId:
        sessionId = PrometheusChatManager.createSession(db, user["userId"], query[:30] + "...")
    else:
        verifySessionOwnsership(db, sessionId, user["userId"])

    response = await Prometheus().sendMessage(query, sessionId=sessionId, db=db)

    return {"success": True, "response": response, "sessionId": sessionId, "timestamp": str(time.time())}


@router.post("/chat/stream")
@limiter.limit("5/minute")
async def chat_stream(
    request: Request,
    db: Session = Depends(getSession),
    query: str = Body(..., min_length=1, max_length=10000, embed=True),
    sessionId: str = Body(default=None, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    if not sessionId:
        sessionId = PrometheusChatManager.createSession(db, user["userId"], query[:30] + "...")
    else:
        verifySessionOwnsership(db, sessionId, user["userId"])

    async def eventStream():
        try:
            async for event in Prometheus().streamMessage(query, sessionId=sessionId, db=db):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            logger.error(f"Stream error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(eventStream(), media_type="text/event-stream")
