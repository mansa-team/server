from fastapi import HTTPException
from datetime import datetime, timedelta
from pytz import timezone
import bcrypt
import jwt

from main.app.authentication.constants import SECRET_KEY, ALGORITHM, TOKEN_EXPIRY_HOURS


def hashPassword(password: str):
    if not password:
        raise ValueError("Password cannot be empty")
    pwdBytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pwdBytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verifyPassword(plainPassword: str | None, hashedPassword: str | None) -> bool:
    if not plainPassword or not hashedPassword:
        return False
    try:
        return bcrypt.checkpw(plainPassword.encode("utf-8"), hashedPassword.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def createAccessToken(data: dict | None, expiresDelta: timedelta | None = None):
    if data is None:
        data = {}
    if expiresDelta is None:
        expiresDelta = timedelta(hours=TOKEN_EXPIRY_HOURS)

    payload = data.copy()
    payload["exp"] = datetime.now(timezone("America/Sao_Paulo")) + expiresDelta

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expiresDelta


def verifyAccessToken(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
