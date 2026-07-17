from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.orm import relationship
from main.models.base import Base


class User(Base):
    __tablename__ = "users"

    userId = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    passwordHash = Column(Text, nullable=True)
    googleId = Column(String(255), unique=True, nullable=True, index=True)
    roles = Column(Text, nullable=True, default="USER")
    createdAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

    sessions = relationship("UserSession", back_populates="user", cascade="all, delete-orphan")
