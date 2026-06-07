from config import Config, getSession

from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

import secrets

from main.models import StocksAPIKey

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader), db: Session = Depends(getSession)):
    if not Config.STOCKS_API["KEY.SYSTEM"]:
        return None

    if not apiKey:
        raise HTTPException(status_code=401, detail="Missing API key")

    try:
        stocksKey = db.query(StocksAPIKey).filter(StocksAPIKey.apiKey == apiKey).first()

        if not stocksKey:
            raise HTTPException(status_code=401, detail="Invalid API key")

        if stocksKey.isQuotaExceeded():
            raise HTTPException(status_code=429, detail="quota exceeded")

        stocksKey.incrementUsage()
        db.commit()

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
    newKey = generateSecureKey(32)
    quota = Config.STOCKS_API["DEFAULT.QUOTA"]

    try:
        existingKey = db.query(StocksAPIKey).filter(StocksAPIKey.userId == userId).first()

        if existingKey:
            existingKey.apiKey = newKey
            existingKey.requestLimit = quota
        else:
            newKeyObj = StocksAPIKey(apiKey=newKey, userId=userId, requestLimit=quota, currentUsage=0)
            db.add(newKeyObj)

        db.commit()
        return newKey

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create API key")
