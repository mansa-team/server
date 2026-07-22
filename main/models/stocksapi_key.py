from sqlalchemy import Integer, String, TIMESTAMP, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from main.models.base import Base
from datetime import datetime


class StocksAPIKey(Base):
    __tablename__ = "stocksapi_keys"

    apiKey: Mapped[str] = mapped_column(String(255), primary_key=True)
    userId: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.userId", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    requestLimit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    currentUsage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lastReset: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

    user = relationship("User")
