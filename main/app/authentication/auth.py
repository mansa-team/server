from imports import *
from main.utils.util import log

from fastapi import HTTPException
from main.app.authentication.util import *

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
                INSERT INTO users (username, email, passwordHash, googleId, roles) 
                VALUES (:u, :e, :p, :g, 'USER')
            """),
            {"u": username, "e": email, "p": hashedPassword, "g": googleId}
        )
        log("auth", f"User created: {username} ({email})")
        return True
    
def authenticateGoogleUser(googleId: str):
    with dbEngine.connect() as conn:
        query = text("SELECT userId, username, email, roles FROM users WHERE googleId = :g")
        user = conn.execute(query, {"g": googleId}).fetchone()
        
        if user:
            log("auth", f"Google Login: {user.username}")
            roles_list = [r.strip() for r in user.roles.split(',')] if user.roles else ['USER']
            return {
                "userId": user.userId,
                "username": user.username,
                "roles": roles_list
            }
    return None

def authenticateUser(username, password):
    with dbEngine.connect() as conn:
        query = text("SELECT userId, username, passwordHash, roles FROM users WHERE username = :u")
        user = conn.execute(query, {"u": username}).fetchone()
        
        if user and user.passwordHash and verifyPassword(password, user.passwordHash):
            log("auth", f"Password Login: {user.username}")
            roles_list = [r.strip() for r in user.roles.split(',')] if user.roles else ['USER']
            return {
                "userId": user.userId,
                "username": user.username,
                "roles": roles_list
            }
    return None

def addRoleToUser(userId: int, role: str):
    with dbEngine.connect() as conn:
        query = text("SELECT roles FROM users WHERE userId = :id")
        user = conn.execute(query, {"id": userId}).fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        roles_raw = getattr(user, 'roles', '')
        currentRoles = [r.strip() for r in roles_raw.split(',')] if roles_raw else []
        if role not in currentRoles:
            currentRoles.append(role)
            newRoles = ",".join(currentRoles)
            
            with dbEngine.begin() as upd:
                upd.execute(
                    text("UPDATE users SET roles = :r WHERE userId = :id"),
                    {"r": newRoles, "id": userId}
                )
            log("auth", f"Added role {role} to user ID {userId}")
            return True
    return False