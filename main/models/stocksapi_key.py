from sqlalchemy import Column, Integer, String, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import relationship
from main.models.base import Base
from datetime import datetime


class StocksAPIKey(Base): 
    __tablename__ = 'stocksapi_keys'

    apiKey = Column(String(255), primary_key=True)
    userId = Column(Integer, ForeignKey('users.userId', ondelete='CASCADE'), unique=True, nullable=False, index=True)
    requestLimit = Column(Integer, nullable=False, default=100)
    currentUsage = Column(Integer, nullable=False, default=0)
    lastReset = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    
    user = relationship("User", back_populates="stocksapi_keys")
    
    def __repr__(self):
        return f"<StocksAPIKey(apiKey='{self.apiKey[:8]}...', userId={self.userId}, usage={self.currentUsage}/{self.requestLimit})>"
    
    def isQuotaExceeded(self) -> bool:
        return self.currentUsage >= self.requestLimit
    
    def needsReset(self, resetDays: int) -> bool:
        if not self.lastReset:
            return True
        daysSinceReset = (datetime.now() - self.lastReset).days
        return daysSinceReset >= resetDays
    
    def resetQuota(self):
        self.currentUsage = 0
        self.lastReset = datetime.now()
    
    def incrementUsage(self):
        self.currentUsage += 1
    
    def getRemainingQuota(self) -> int:
        return max(0, self.requestLimit - self.currentUsage)
    
    def toDict(self):
        return {
            'apiKey': self.apiKey,
            'userId': self.userId,
            'requestLimit': self.requestLimit,
            'currentUsage': self.currentUsage,
            'remainingQuota': self.getRemainingQuota(),
            'lastReset': self.lastReset.isoformat() if self.lastReset else None
        }