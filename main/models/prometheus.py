from sqlalchemy import Column, Integer, String, Text, ForeignKey, TIMESTAMP, Enum, JSON, func
from sqlalchemy.orm import relationship
from main.models.base import Base

class PrometheusSession(Base):
    __tablename__ = 'prometheus'

    sessionId = Column(String(255), primary_key=True)
    userId = Column(Integer, ForeignKey('users.userId', ondelete='CASCADE'), nullable=False)
    title = Column(String(255))
    summary = Column(Text)
    history = Column(JSON, default=[])
    lastActivity = Column(TIMESTAMP, server_default=func.now(), onupdate=func.now())
    createdAt = Column(TIMESTAMP, server_default=func.now())

    user = relationship("User")