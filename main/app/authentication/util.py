from fastapi import HTTPException
from datetime import datetime, timedelta
import jwt
import bcrypt

from main.app.authentication.constants import SECRET_KEY, ALGORITHM, TOKEN_EXPIRY_HOURS

def hashPassword(password: str):
    pwdBytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pwdBytes, bcrypt.gensalt())
    return hashed.decode("utf-8")

def verifyPassword(plainPassword: str, hashedPassword: str) -> bool:
    try:
        return bcrypt.checkpw(plainPassword.encode("utf-8"), hashedPassword.encode("utf-8"))
    except (ValueError, TypeError):
        return False

def createAccessToken(data: dict, expiresDelta: timedelta = None):
    from main.utils.util import log

    if expiresDelta is None:
        expiresDelta = timedelta(hours=TOKEN_EXPIRY_HOURS)

    payload = data.copy()
    payload["exp"] = (datetime.utcnow() + expiresDelta).timestamp()

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    log("auth", "Token created successfully")
    return token

def verifyAccessToken(token: str) -> dict:
    from main.utils.util import log

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        log("auth", "Token verified successfully")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")