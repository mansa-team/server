import logging
from config import SessionLocal
from main.models import PrometheusSession
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified
import uuid

logger = logging.getLogger(__name__)


class PrometheusChatManager:
    def __init__(self):
        pass

    @classmethod
    def getUserSessions(cls, userId: int):
        db = SessionLocal()
        try:
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
        finally:
            db.close()

    @classmethod
    def createSession(cls, userId: int, title: str = "New Conversation"):
        db = SessionLocal()
        sessionId = str(uuid.uuid4())
        try:
            newSession = PrometheusSession(sessionId=sessionId, userId=userId, title=title, history=[])
            db.add(newSession)
            db.commit()
            return sessionId
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating session: {str(e)}", exc_info=True)
            raise e
        finally:
            db.close()

    @classmethod
    def updateSessionTitle(cls, sessionId: str, title: str):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()

            if not session:
                return False

            session.title = title
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating session title: {str(e)}", exc_info=True)
            return False
        finally:
            db.close()

    @classmethod
    def saveMessage(cls, sessionId: str, role: str, content: str, metadata: dict | None = None):
        db = SessionLocal()
        try:
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
        except Exception as e:
            db.rollback()
            logger.error(f"Error saving message to JSON: {str(e)}", exc_info=True)
        finally:
            db.close()

    @classmethod
    def getHistory(cls, sessionId: str, limit: int = 20):
        db = SessionLocal()
        try:
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
        finally:
            db.close()

    @classmethod
    def updateSummary(cls, sessionId: str, summary: str):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
            if session:
                session.summary = summary
                db.commit()
        finally:
            db.close()

    @classmethod
    def deleteSession(cls, sessionId: str, userId: int):
        db = SessionLocal()
        try:
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
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting session: {str(e)}", exc_info=True)
            return False
        finally:
            db.close()

    @classmethod
    def verifySessionOwnership(cls, sessionId: str, userId: int) -> bool:
        db = SessionLocal()
        try:
            exists = (
                db.query(PrometheusSession.sessionId)
                .filter(PrometheusSession.sessionId == sessionId, PrometheusSession.userId == userId)
                .first()
                is not None
            )
            return exists
        finally:
            db.close()
