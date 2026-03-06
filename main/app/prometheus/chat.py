from config import SessionLocal
from main.models import PrometheusSession
from main.utils.util import log
from datetime import datetime
from sqlalchemy.orm.attributes import flag_modified
import uuid

class PrometheusChatManager:
    def __init__(self):
        pass

    def getUserSessions(self, userId: int):
        db = SessionLocal()
        try:
            sessions = db.query(
                PrometheusSession.sessionId,
                PrometheusSession.title,
                PrometheusSession.lastActivity
            ).filter(
                PrometheusSession.userId == userId
            ).order_by(PrometheusSession.lastActivity.desc()).limit(30).all()
            
            return [
                {
                    "sessionId": s.sessionId,
                    "title": s.title,
                    "lastActivity": s.lastActivity.isoformat() if s.lastActivity else None
                }
                for s in sessions
            ]
        finally:
            db.close()

    def createSession(self, userId: int, title: str = "New Conversation"):
        db = SessionLocal()
        sessionId = str(uuid.uuid4())
        try:
            newSession = PrometheusSession(
                sessionId=sessionId,
                userId=userId,
                title=title,
                history=[]
            )
            db.add(newSession)
            db.commit()
            return sessionId
        except Exception as e:
            db.rollback()
            log("error", f"Error creating session: {str(e)}")
            raise e
        finally:
            db.close()

    def updateSessionTitle(self, sessionId: str, title: str):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(
                PrometheusSession.sessionId == sessionId
            ).first()
            
            if not session:
                return False
                
            session.title = title
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            log("error", f"Error updating session title: {str(e)}")
            return False
        finally:
            db.close()

    def saveMessage(self, sessionId: str, role: str, content: str, metadata: dict = None):
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
                    "timestamp": datetime.now().isoformat()
                }

                session.history.append(message)
                flag_modified(session, "history")
                
                session.lastActivity = datetime.now()
                db.commit()
            else:
                log("error", f"Session {sessionId} not found for saveMessage")
        except Exception as e:
            db.rollback()
            log("error", f"Error saving message to JSON: {str(e)}")
        finally:
            db.close()

    def getHistory(self, sessionId: str, limit: int = 20):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(
                PrometheusSession.sessionId == sessionId
            ).first()

            if not session or not session.history:
                return []

            activeHistory = session.history[-limit:]
            
            formatted_history = []
            for msg in activeHistory:
                formatted_history.append({
                    "role": "user" if msg['role'] == "user" else "model",
                    "parts": [{"text": msg['content']}]
                })
            return formatted_history
        finally:
            db.close()

    def updateSummary(self, sessionId: str, summary: str):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(PrometheusSession.sessionId == sessionId).first()
            if session:
                session.summary = summary
                db.commit()
        finally:
            db.close()

    def deleteSession(self, sessionId: str, userId: int):
        db = SessionLocal()
        try:
            session = db.query(PrometheusSession).filter(
                PrometheusSession.sessionId == sessionId,
                PrometheusSession.userId == userId
            ).first()
            if session:
                db.delete(session)
                db.commit()
                return True
            return False
        except Exception as e:
            db.rollback()
            log("error", f"Error deleting session: {str(e)}")
            return False
        finally:
            db.close()

    def verifySessionOwnership(self, sessionId: str, userId: int) -> bool:
        db = SessionLocal()
        try:
            exists = db.query(PrometheusSession.sessionId).filter(
                PrometheusSession.sessionId == sessionId,
                PrometheusSession.userId == userId
            ).first() is not None
            return exists
        finally:
            db.close()

prometheusChatManager = PrometheusChatManager()