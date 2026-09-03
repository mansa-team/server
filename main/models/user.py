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


# Bottom import breaks User <-> UserSession cycle order-independently:
# - Order A (import user first): defines User, then loads UserSession (which
#   reuses the already-defined User) -> both in registry.
# - Order B (import user_session first): user_session pulls User; this bottom
#   import hits the partially-initialized user_session module and raises
#   ImportError, which we swallow — user_session completes right after, so by
#   mapper-configure time (first instantiation) both classes exist.
try:
    from main.models.user_session import UserSession  # noqa: F401
except ImportError:
    pass
