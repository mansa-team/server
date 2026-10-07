import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from config import SessionLocal, getSession, Config
from main.utils.logging_config import limiter
from main.utils.request_id import requestIdVar

from main.models.orunmila import OrunmilaSession
from main.utils.roles import Roles, Permission

from main.app.orunmila.agent import Orunmila
from main.app.orunmila.chat import OrunmilaChatManager
from main.app.orunmila.stream_bus import streamBus
from main.app.orunmila.sandbox import SandboxManager, hostPath
from main.app.authentication.util import extractRawToken

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orunmila", tags=["Orunmila"])


def verifySessionOwnsership(db: Session, sessionId: str, userId: int):
    if not OrunmilaChatManager.verifySessionOwnership(db, sessionId, userId):
        raise HTTPException(status_code=403, detail="Forbidden: You do not own this session")


@router.get("/health")
def health():
    return {"status": "ok", "service": "orunmila"}


@router.get("/sessions")
def getSessions(
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
    limit: int = Query(20, ge=1, le=100, description="Number of items per page"),
    offset: int = Query(0, ge=0, description="Number of items to skip"),
):
    sessions = OrunmilaChatManager.getUserSessions(db, user["userId"])
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
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])

    success = OrunmilaChatManager.updateSessionTitle(db, sessionId, title)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"success": True, "message": "Session title updated"}


@router.get("/history/{sessionId}")
def getHistory(
    sessionId: str,
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])
    session = (
        db.query(OrunmilaSession)
        .filter(OrunmilaSession.sessionId == sessionId, OrunmilaSession.userId == user["userId"])
        .first()
    )

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"success": True, "history": session.history or []}


@router.delete("/sessions/{sessionId}")
def deleteSession(
    sessionId: str,
    db: Session = Depends(getSession),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    success = OrunmilaChatManager.deleteSession(db, sessionId, user["userId"])
    if not success:
        raise HTTPException(status_code=404, detail="Session not found or forbidden")
    return {"success": True, "message": "Session deleted"}


@router.post("/chat/stream")
@limiter.limit("5/minute")
async def chat_stream(
    request: Request,
    db: Session = Depends(getSession),
    query: str = Form(..., min_length=1, max_length=10000),
    sessionId: str = Form(default=None),
    file: UploadFile | None = File(default=None),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    if not sessionId:
        sessionId = OrunmilaChatManager.createSession(db, user["userId"], query[:30] + "...")
    else:
        verifySessionOwnsership(db, sessionId, user["userId"])

    file_data = None
    if file is not None:
        maxBytes = Config.ORUNMILA.WORKSPACE_MAX_UPLOAD_MB * 1024 * 1024
        content = await file.read(maxBytes + 1)
        if len(content) > maxBytes:
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds {Config.ORUNMILA.WORKSPACE_MAX_UPLOAD_MB}MB limit",
            )
        file_data = {
            "name": file.filename,
            "content": content,
            "mime": file.content_type or "application/octet-stream",
        }

    correlationId = requestIdVar.get("") or uuid.uuid4().hex
    requestIdVar.set(correlationId)

    # Raw session JWT (not the decoded payload) — forwarded to MCP-bound wallet
    # tool calls by the dispatcher; transport headers on the shared MCP pool are
    # frozen, so the token rides as a call argument instead.
    rawToken = extractRawToken(request)

    async def runner() -> AsyncIterator[dict]:
        runDb = SessionLocal()
        try:
            yield {"type": "session", "sessionId": sessionId}
            async for event in Orunmila().streamMessage(
                query, sessionId=sessionId, db=runDb, user=user, file=file_data, rawToken=rawToken
            ):
                yield event
        except Exception as e:
            logger.exception("Stream run error for session %s (correlation_id=%s)", sessionId, correlationId)
            yield {"type": "error", "message": "stream failed", "correlationId": correlationId}
        finally:
            runDb.close()

    streamBus.startRun(sessionId, runner)

    return streamBus.streamResponse(sessionId, cursor=0)


@router.get("/chat/stream/{sessionId}")
async def resumeChatStream(
    sessionId: str,
    db: Session = Depends(getSession),
    cursor: int = Query(0, ge=0),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    verifySessionOwnsership(db, sessionId, user["userId"])
    return streamBus.streamResponse(sessionId, cursor=cursor)


@router.delete("/workspace/delete")
@limiter.limit("30/minute")
def deleteWorkspaceFile(
    request: Request,
    db: Session = Depends(getSession),
    path: str = Body(..., min_length=1, max_length=1000, embed=True),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    ok = SandboxManager.delete_file(user["userId"], path)
    if not ok:
        raise HTTPException(status_code=404, detail="File not found or directory not empty")
    return {"success": True, "path": path}


@router.get("/workspace/download")
def downloadWorkspaceFile(
    db: Session = Depends(getSession),
    path: str = Query(..., min_length=1, max_length=1000),
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
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
    user: dict = Depends(Roles.requirePermission(Permission.USE_ORUNMILA)),
):
    try:
        return SandboxManager.list_files(user["userId"], path)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid workspace path")
