from config import Config, getSession

from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import update
from sqlalchemy.orm import Session

import secrets
import hashlib

from main.models import StocksAPIKey

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)


def _hash_key(key: str) -> str:
    """Return SHA-256 hex digest of the given key."""
    return hashlib.sha256(key.encode()).hexdigest()


async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader), db: Session = Depends(getSession)):
    if not Config.STOCKS_API["KEY.SYSTEM"]:
        return None

    if not apiKey:
        raise HTTPException(status_code=401, detail="Missing API key")

    hashedKey = _hash_key(apiKey)

    try:
        # Atomic check-and-increment: prevents TOCTOU race condition
        # The UPDATE only succeeds if currentUsage < requestLimit,
        # ensuring quota is never exceeded even under concurrent requests
        result = db.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == hashedKey)
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        db.commit()

        if result.rowcount == 0:
            # Either key doesn't exist or quota is exceeded
            # Check which case to return the correct error
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
    return secrets.token_urlsafe(length)[:length]


def createKey(db: Session, userId: int):
    rawKey = generateSecureKey(32)
    hashedKey = _hash_key(rawKey)
    quota = Config.STOCKS_API["DEFAULT.QUOTA"]

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

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create API key")
