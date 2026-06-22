from sqlalchemy import Column, Integer, String, TIMESTAMP, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from main.models.base import Base


class UserSession(Base):
    __tablename__ = "user_sessions"

    sessionId = Column(String(64), primary_key=True)
    userId = Column(Integer, ForeignKey("users.userId"), nullable=False, index=True)
    accessTokenHash = Column(String(64), nullable=False)
    deviceType = Column(String(20), nullable=True)
    browser = Column(String(50), nullable=True)
    operatingSystem = Column(String(50), nullable=True)
    userAgent = Column(String(500), nullable=True)
    isActive = Column(Boolean, default=True, nullable=False)
    createdAt = Column(TIMESTAMP, nullable=True)
    lastActivityAt = Column(TIMESTAMP, nullable=True)
    expiresAt = Column(TIMESTAMP, nullable=True)

    user = relationship("User", back_populates="sessions")

    def getDeviceName(self) -> str:
        if self.browser and self.operatingSystem:
            return f"{self.browser} on {self.operatingSystem}"
        elif self.accessTokenHash:
            return f"Device {self.accessTokenHash[:8]}"
        return "Unknown Device"
