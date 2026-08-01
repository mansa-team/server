from config import Config, getSession

from typing import cast
import secrets
import hashlib

from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from main.models import StocksAPIKey

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)


def hashKey(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader), db: Session = Depends(getSession)):
    if not Config.STOCKS_API.KEY_SYSTEM:
        return None

    if not apiKey:
        raise HTTPException(status_code=401, detail="Missing API key")

    hashedKey = hashKey(apiKey)

    try:
        result = db.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == hashedKey)
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        db.commit()

        if cast(CursorResult, result).rowcount == 0:
            stocksKey = db.query(StocksAPIKey).filter(StocksAPIKey.apiKey == hashedKey).first()
            if not stocksKey:
                raise HTTPException(status_code=401, detail="Invalid API key")
            else:
                raise HTTPException(status_code=429, detail="quota exceeded")

        return apiKey

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="API key verification failed")


def generateSecureKey(length: int = 32) -> str:
    return secrets.token_hex(length // 2)


def createKey(db: Session, userId: int):
    rawKey = generateSecureKey(32)
    hashedKey = hashKey(rawKey)
    quota = Config.STOCKS_API.DEFAULT_QUOTA

    try:
        existingKey = db.query(StocksAPIKey).filter(StocksAPIKey.userId == userId).first()

        if existingKey:
            existingKey.apiKey = hashedKey
            existingKey.requestLimit = quota
        else:
            newKeyObj = StocksAPIKey(apiKey=hashedKey, userId=userId, requestLimit=quota, currentUsage=0)
            db.add(newKeyObj)

        db.commit()
        return rawKey

    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create API key")
