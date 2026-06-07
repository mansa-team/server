import logging
from main.models import PrometheusSession
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
import uuid

logger = logging.getLogger(__name__)


class PrometheusChatManager:
    def __init__(self):
        pass

    @classmethod
    def getUserSessions(cls, db: Session, userId: int):
        sessions = (
            db.query(PrometheusSession.sessionId, PrometheusSession.title, PrometheusSession.lastActivity)
            .filter(PrometheusSession.userId == userId)
            .order_by(PrometheusSession.lastActivity.desc())
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
        newSession = PrometheusSession(sessionId=sessionId, userId=userId, title=title, history=[])
        db.add(newSession)
        db.commit()
        return sessionId

    @classmethod
    def updateSessionTitle(cls, db: Session, sessionId: str, title: str):
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if not session:
            return False

        session.title = title
        db.commit()
        return True

    @classmethod
    def saveMessage(cls, db: Session, sessionId: str, role: str, content: str, metadata: dict | None = None):
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if session:
            if session.history is None:
                session.history = []

            message = {
                "role": role,
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now().isoformat(),
            }

            session.history.append(message)
            flag_modified(session, "history")

            session.lastActivity = datetime.now()
            db.commit()
        else:
            logger.error(f"Session {sessionId} not found for saveMessage")

    @classmethod
    def getHistory(cls, db: Session, sessionId: str, limit: int = 20):
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

        if not session or not session.history:
            return []

        activeHistory = session.history[-limit:]

        formattedHistory = []
        for msg in activeHistory:
            formattedHistory.append(
                {"role": "user" if msg["role"] == "user" else "model", "parts": [{"text": msg["content"]}]}
            )
        return formattedHistory

    @classmethod
    def updateSummary(cls, db: Session, sessionId: str, summary: str):
        session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
        if session:
            session.summary = summary
            db.commit()

    @classmethod
    def deleteSession(cls, db: Session, sessionId: str, userId: int):
        session = (
            db.query(PrometheusSession)
            .filter(PrometheusSession.sessionId == sessionId, PrometheusSession.userId == userId)
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
            db.query(PrometheusSession.sessionId)
            .filter(PrometheusSession.sessionId == sessionId, PrometheusSession.userId == userId)
            .first()
            is not None
        )
        return exists
