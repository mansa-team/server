from imports import *

from fastapi import Depends, HTTPException, status
from main.app.auth.util import *

def createUserAccount(username, email, password):
    hashedPassword = hashPassword(password)

    with dbEngine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO users (username, email, passwordHash, accessLevel) 
                VALUES (:u, :e, :p, 0)
            """),
            {"u": username, "e": email, "p": hashedPassword}
        )
        return True
    
def authenticateUser(username, password):
    with dbEngine.connect() as conn:
        query = text("SELECT userId, username, passwordHash, accessLevel FROM users WHERE username = :u")
        user = conn.execute(query, {"u": username}).fetchone()
        
        if user and verifyPassword(password, user.passwordHash):
            return {
                "userId": user.userId,
                "username": user.username,
                "accessLevel": user.accessLevel
            }
    return None