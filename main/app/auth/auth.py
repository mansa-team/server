from imports import *
from main.utils.util import log

from fastapi import Depends, HTTPException, status
from main.app.auth.util import *

def createUserAccount(username, email, password=None, googleId=None):
    if not password and not googleId:
        raise HTTPException(
            status_code=400, 
            detail="Account must have either a password."
        )
    
    with dbEngine.connect() as conn:
        existingUser = conn.execute(
            text("SELECT username, email FROM users WHERE username = :u OR email = :e LIMIT 1"),
            {"u": username, "e": email}
        ).fetchone()
        
        if existingUser:
            if existingUser.username == username:
                detail = "Username already taken."
            else:
                detail = "Email already registered."
            raise HTTPException(status_code=400, detail=detail)

    hashedPassword = hashPassword(password) if password else None

    with dbEngine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO users (username, email, passwordHash, googleId, accessLevel) 
                VALUES (:u, :e, :p, :g, 0)
            """),
            {"u": username, "e": email, "p": hashedPassword, "g": googleId}
        )
        log("auth", f"User created: {username} ({email})")
        return True
    
def authenticateGoogleUser(googleId: str):
    with dbEngine.connect() as conn:
        query = text("SELECT userId, username, email, accessLevel FROM users WHERE googleId = :g")
        user = conn.execute(query, {"g": googleId}).fetchone()
        
        if user:
            log("auth", f"Google Login: {user.username}")
            return {
                "userId": user.userId,
                "username": user.username,
                "accessLevel": user.accessLevel
            }
    return None

def authenticateUser(username, password):
    with dbEngine.connect() as conn:
        query = text("SELECT userId, username, passwordHash, accessLevel FROM users WHERE username = :u")
        user = conn.execute(query, {"u": username}).fetchone()
        
        if user and user.passwordHash and verifyPassword(password, user.passwordHash):
            log("auth", f"Password Login: {user.username}")
            return {
                "userId": user.userId,
                "username": user.username,
                "accessLevel": user.accessLevel
            }
    return None