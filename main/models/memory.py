from sqlalchemy import Column, Integer, String, Text, Float, DateTime, UniqueConstraint, Index, func
from sqlalchemy.orm import relationship
from main.models.base import Base
from main.models.memory_types import VectorType


class UserMemory(Base):
    __tablename__ = "prometheus_memories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, nullable=False, index=True)
    memoryKey = Column(String(100), nullable=False)
    memoryValue = Column(Text, nullable=False)
    memoryType = Column(String(20), default="context")
    source = Column(String(20), default="inferred")
    baseScore = Column(Float, default=1.0)
    accessCount = Column(Integer, default=0)
    embedding = Column(VectorType(384))  # type: ignore[var-annotated]
    contentHash = Column(String(32))
    createdAt = Column(DateTime, server_default=func.now())
    updatedAt = Column(DateTime, server_default=func.now(), onupdate=func.now())
    lastAccessedAt = Column(DateTime, nullable=True)
    archivedAt = Column(DateTime, nullable=True)

    user = relationship(
        "User", backref="memories", foreign_keys=[userId], primaryjoin="UserMemory.userId == User.userId"
    )

    __table_args__ = (
        UniqueConstraint("userId", "memoryKey", name="uk_prometheus_memories"),
        Index("idx_relevance", "userId", "baseScore"),
        Index("idx_type", "userId", "memoryType"),
    )
