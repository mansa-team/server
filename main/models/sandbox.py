from sqlalchemy import Column, Integer, String, DateTime, func
from main.models.base import Base


class OrunmilaSandbox(Base):
    __tablename__ = "orunmila_sandboxes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, nullable=False, index=True, unique=True)
    sandboxId = Column(String(255), nullable=False)
    lastActivity = Column(DateTime, server_default=func.now(), onupdate=func.now())
    createdAt = Column(DateTime, server_default=func.now())
