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
