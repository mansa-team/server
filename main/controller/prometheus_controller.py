import asyncio
import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.orm import Session

from config import SessionLocal, getSession, Config
from main.utils.logging_config import limiter

from main.models.prometheus import PrometheusSession
from main.utils.roles import Roles, Permission

from main.app.prometheus.agent import Prometheus
from main.app.prometheus.chat import PrometheusChatManager
from main.app.prometheus.stream_bus import streamBus
from main.app.prometheus.sandbox import SandboxManager, hostPath

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

    async def runner() -> AsyncIterator[dict]:
        runDb = SessionLocal()
        try:
            yield {"type": "session", "sessionId": sessionId}
            async for event in Prometheus().streamMessage(query, sessionId=sessionId, db=runDb, user=user):
                yield event
        except Exception as e:
            logger.error("Stream run error for session %s: %s", sessionId, e)
            yield {"type": "error", "message": str(e)}
        finally:
            runDb.close()

    streamBus.startRun(sessionId, runner)

    return StreamingResponse(_forward(sessionId, cursor=0), media_type="text/event-stream")


@router.get("/chat/stream/{sessionId}")
async def resumeChatStream(
    sessionId: str,
    db: Session = Depends(getSession),
    cursor: int = Query(0, ge=0),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    # No rate limiter: this route only subscribes to an existing run; the
    # POST 5/minute limiter gates starting new runs.
    verifySessionOwnsership(db, sessionId, user["userId"])
    return StreamingResponse(_forward(sessionId, cursor=cursor), media_type="text/event-stream")


@router.post("/workspace/upload")
@limiter.limit("10/minute")
async def uploadWorkspaceFile(
    request: Request,
    db: Session = Depends(getSession),
    path: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    maxBytes = Config.PROMETHEUS.WORKSPACE_MAX_UPLOAD_MB * 1024 * 1024
    content = await file.read(maxBytes + 1)
    if len(content) > maxBytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds {Config.PROMETHEUS.WORKSPACE_MAX_UPLOAD_MB}MB limit",
        )

    ok = SandboxManager.write_bytes(user["userId"], path, content)
    if not ok:
        raise HTTPException(status_code=400, detail="Invalid workspace path")
    return {"success": True, "path": path, "size": len(content)}


@router.delete("/workspace/delete")
@limiter.limit("30/minute")
def deleteWorkspaceFile(
    request: Request,
    db: Session = Depends(getSession),
    path: str = Body(..., min_length=1, max_length=1000, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    ok = SandboxManager.delete_file(user["userId"], path)
    if not ok:
        raise HTTPException(status_code=404, detail="File not found or directory not empty")
    return {"success": True, "path": path}


@router.get("/workspace/download")
def downloadWorkspaceFile(
    db: Session = Depends(getSession),
    path: str = Query(..., min_length=1, max_length=1000),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    try:
        host = hostPath(user["userId"], path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace path")

    if not host.exists() or not host.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(host, filename=host.name)


@router.get("/workspace/list")
def listWorkspaceFiles(
    db: Session = Depends(getSession),
    path: str = Query("/workspace", max_length=1000),
    user: dict = Depends(Roles.requirePermission(Permission.USE_PROMETHEUS)),
):
    return SandboxManager.list_files(user["userId"], path)


async def _forward(sessionId: str, cursor: int = 0) -> AsyncIterator[str]:
    sub = streamBus.subscribe(sessionId, cursor)
    if sub is None:
        yield "data: [DONE]\n\n"
        return
    q, _ch = sub
    try:
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=30)
            except asyncio.TimeoutError:
                if _ch.finished:
                    # Channel is done but this subscriber missed the done event
                    # (queue overflow or cursor == len(events)): terminate instead
                    # of streaming keepalives forever.
                    yield "data: " + json.dumps({"type": "done"}) + "\n\n"
                    yield "data: [DONE]\n\n"
                    return
                yield ": keepalive\n\n"  # SSE comment line keeps proxies happy
                continue
            yield f"data: {json.dumps(event)}\n\n"
            if event.get("type") == "done":
                yield "data: [DONE]\n\n"
                return
    finally:
        streamBus.unsubscribe(sessionId, q)
