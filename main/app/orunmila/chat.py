import logging
from datetime import datetime
import uuid

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from main.models.orunmila import OrunmilaSession

logger = logging.getLogger(__name__)


class OrunmilaChatManager:
    @classmethod
    def getUserSessions(cls, db: Session, userId: int):
        sessions: list = (
            db.query(OrunmilaSession.sessionId, OrunmilaSession.title, OrunmilaSession.lastActivity)
            .filter(OrunmilaSession.userId == userId)
            .order_by(OrunmilaSession.lastActivity.desc())
            .all()
        )

        return [
            {
                "sessionId": s.sessionId,
                "title": s.title,
                "lastActivity": s.lastActivity.isoformat() if s.lastActivity else None,
            }
            for s in sessions
        ]

    @classmethod
    def createSession(cls, db: Session, userId: int, title: str = "New Conversation"):
        sessionId = str(uuid.uuid4())
        newSession = OrunmilaSession(sessionId=sessionId, userId=userId, title=title, history=[])
        db.add(newSession)
        db.commit()
        return sessionId

    @classmethod
    def updateSessionTitle(cls, db: Session, sessionId: str, title: str):
        session = db.query(OrunmilaSession).filter(OrunmilaSession.sessionId == sessionId).first()

        if not session:
            return False

        session.title = title  # type: ignore[assignment]
        db.commit()
        return True

    @classmethod
    def appendHistory(cls, db: Session, sessionId: str, entry: dict):
        session = db.query(OrunmilaSession).filter(OrunmilaSession.sessionId == sessionId).first()

        if session:
            if session.history is None:
                session.history = []

            entry["timestamp"] = datetime.now().isoformat()

            session.history.append(entry)

            flag_modified(session, "history")

            session.lastActivity = datetime.now()  # type: ignore[assignment]
            db.commit()
        else:
            logger.error(f"Session {sessionId} not found for appendHistory")

    @classmethod
    def getHistory(cls, db: Session, sessionId: str, limit: int = 20, since: datetime | None = None):
        session = db.query(OrunmilaSession).filter(OrunmilaSession.sessionId == sessionId).first()

        if not session or not session.history:
            return []

        activeHistory: list = session.history[-limit:]  # type: ignore[assignment]

        if since is not None:
            activeHistory = [m for m in activeHistory if m.get("timestamp", "") > since.isoformat()]

        formattedHistory = []
        for msg in activeHistory:
            if msg.get("role") == "loop_event":
                continue
            formattedHistory.append(
                {"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]}
            )
        return formattedHistory

    @classmethod
    def deleteSession(cls, db: Session, sessionId: str, userId: int):
        session = (
            db.query(OrunmilaSession)
            .filter(OrunmilaSession.sessionId == sessionId, OrunmilaSession.userId == userId)
            .first()
        )

        if session:
            db.delete(session)
            db.commit()
            return True
        return False

    @classmethod
    def verifySessionOwnership(cls, db: Session, sessionId: str, userId: int) -> bool:
        exists = (
            db.query(OrunmilaSession.sessionId)
            .filter(OrunmilaSession.sessionId == sessionId, OrunmilaSession.userId == userId)
            .first()
            is not None
        )
        return exists
