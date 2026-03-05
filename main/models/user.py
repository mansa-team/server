from sqlalchemy import Column, Integer, String, Text, TIMESTAMP, func
from sqlalchemy.orm import relationship
from main.models.base import Base


class User(Base):
    __tablename__ = 'users'

    userId = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(255), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    passwordHash = Column(Text, nullable=True)
    googleId = Column(String(255), unique=True, nullable=True, index=True)
    roles = Column(Text, nullable=True, default='USER')
    createdAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)
    stocksapi_keys = relationship(
        "StocksAPIKey",
        back_populates="user",
        cascade="all, delete-orphan",
        uselist=False  # one2one relationship
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
