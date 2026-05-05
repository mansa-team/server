from sqlalchemy import Integer, String, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from main.models.base import Base
from datetime import datetime, timezone


class StocksAPIKey(Base):
    __tablename__ = "stocksapi_keys"

    apiKey: Mapped[str] = mapped_column(String(255), primary_key=True)
    userId: Mapped[int] = mapped_column(Integer, ForeignKey("users.userId", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    requestLimit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    currentUsage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lastReset: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

    user = relationship("User", back_populates="stocksapi_keys")

    def __repr__(self):
        return f"<StocksAPIKey(apiKey='{self.apiKey[:8]}...', userId={self.userId}, usage={self.currentUsage}/{self.requestLimit})>"

    def isQuotaExceeded(self) -> bool:
        return self.currentUsage >= self.requestLimit

    def needsReset(self, resetDays: int) -> bool:
        if not self.lastReset:
            return True
        now = datetime.now(timezone.utc)
        lastResetTime = self.lastReset.replace(tzinfo=timezone.utc) if self.lastReset.tzinfo is None else self.lastReset
        daysSinceReset = (now - lastResetTime).days
        return daysSinceReset >= resetDays

    def resetQuota(self):
        self.currentUsage = 0
        self.lastReset = datetime.now(timezone.utc)

    def incrementUsage(self):
        self.currentUsage += 1

    def getRemainingQuota(self) -> int:
        return max(0, self.requestLimit - self.currentUsage)

    def toDict(self):
        return {
            "apiKey": self.apiKey,
            "userId": self.userId,
            "requestLimit": self.requestLimit,
            "currentUsage": self.currentUsage,
            "remainingQuota": self.getRemainingQuota(),
            "lastReset": self.lastReset.isoformat() if self.lastReset else None,
        }