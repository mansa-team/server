from imports import *

from fastapi import HTTPException, Security, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
import bcrypt

security = HTTPBearer()
SECRET_KEY = Config.AUTH['JEW_TOKEN']
ALGORITHM = "HS256"

levels = {
    "Free": 00,
    "Premium": 10,
    "Developer": 1,
    "Premium Developer": 11,
    "Admin": 67
}

def hashPassword(password: str):
    pwdBytes = password.encode('utf-8')
    hashed = bcrypt.hashpw(pwdBytes, bcrypt.gensalt())
    return hashed.decode('utf-8')

def verifyPassword(plainPassword: str, hashedPassword: str) -> bool:
    try:
        return bcrypt.checkpw(
            plainPassword.encode('utf-8'), 
            hashedPassword.encode('utf-8')
        )
    except Exception:
        return False

def createAccessToken(data: dict, expiresDelta: timedelta = timedelta(hours=24)):
    toEncode = data.copy()
    expire = datetime.utcnow() + expiresDelta
    toEncode.update({"exp": int(expire.timestamp())})

    return jwt.encode(toEncode, SECRET_KEY, algorithm=ALGORITHM)

def checkAccessLevel(currentLevel: int, requiredLevel: int) -> bool:
    if currentLevel == levels['Admin']: return True
    return currentLevel >= requiredLevel

def getCurrentUser(request: Request):
    token = request.cookies.get("mansa_token")
    
    if not token:
        authHeader = request.headers["Authorization"]
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Session not found")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        userId = payload['userId']

        if userId is None:
            raise HTTPException(status_code=401, detail="Invalid Token")
        return payload
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")