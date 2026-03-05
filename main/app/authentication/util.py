from config import Config, SessionLocal
from main.utils.roles import Roles

from fastapi import HTTPException, Request
from fastapi.security import HTTPBearer
from datetime import datetime, timedelta
import jwt
import bcrypt

from main.models import User

security = HTTPBearer()
SECRET_KEY = Config.USER['JEWISH_TOKEN']
ALGORITHM = "HS256"

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

def getCurrentUser(request: Request):
    token = request.cookies.get("mansa_token")
    
    if not token:
        authHeader = request.headers.get("authorization") or request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if not token:
        raise HTTPException(status_code=401, detail="Session not found")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        userId = payload['userId']

        if userId is None:
            raise HTTPException(status_code=401, detail="Invalid Token")

        db = SessionLocal()
        try:
            user = db.query(User).filter(User.userId == userId).first()
            
            if not user:
                raise HTTPException(status_code=401, detail="User no longer exists")
            
            return {
                "userId": user.userId,
                "username": user.username,
                "email": user.email,
                "roles": user.getRolesList()
            }
        
        finally:
            db.close()
            
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")