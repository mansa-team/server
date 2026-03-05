from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.orm import relationship
from main.models import Base


class User(Base):
    __tablename__ = 'users'
    
    # Primary Key
    userId = Column(Integer, primary_key=True, autoincrement=True)
    
    # Authentication Fields
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    passwordHash = Column(Text, nullable=True)  # NULL for Google OAuth
    googleId = Column(String(255), unique=True, nullable=True, index=True)  # NULL for password auth
    
    # Authorization
    roles = Column(Text, nullable=True, default='USER')
    
    # Metadata
    createdAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    
    # Relationships
    stocksapi_keys = relationship(
        "StocksAPIKey",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False  # One-to-one relationship
    )
    
    def __repr__(self):
        return f"<User(userId={self.userId}, username='{self.username}', email='{self.email}')>"
    
    def getRolesList(self):
        if not self.roles:
            return ['USER']
        return [role.strip() for role in self.roles.split(',')]
    
    def addRole(self, role: str):
        currentRoles = self.getRolesList()
        if role not in currentRoles:
            currentRoles.append(role)
            self.roles = ','.join(currentRoles)
    
    def removeRole(self, role: str):
        currentRoles = self.getRolesList()
        if role in currentRoles:
            currentRoles.remove(role)
            self.roles = ','.join(currentRoles) if currentRoles else 'USER'
    
    def hasRole(self, role: str) -> bool:
        return role in self.getRolesList()
    
    def toDict(self):
        return {
            'userId': self.userId,
            'username': self.username,
            'email': self.email,
            'roles': self.getRolesList(),
            'createdAt': self.createdAt.isoformat() if self.createdAt else None
        }
