from config import Config, getSession

from typing import cast
import hashlib

from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from main.models.stocksapi_key import StocksAPIKey

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
