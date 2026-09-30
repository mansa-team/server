import hashlib
import hmac
import secrets
from typing import cast

from config import Config, getStocksSession

from fastapi import Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlalchemy import update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from main.models.stocksapi_key import StocksAPIKey

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)


def hashApiKey(rawKey: str, saltHex: str) -> str:
    return hashlib.sha256((saltHex + rawKey).encode()).hexdigest()


def createStoredApiKey(rawKey: str | None = None) -> tuple[str, str]:
    raw = rawKey or secrets.token_urlsafe(32)
    saltHex = secrets.token_hex(16)
    return raw, f"{saltHex}{'$'}{hashApiKey(raw, saltHex)}"


def isValidStoredKey(providedKey: str, storedKey: str | None) -> bool:
    try:
        if not providedKey or not storedKey or "$" not in storedKey:
            return False
        saltHex, digest = storedKey.split("$", 1)
        if not saltHex or not digest:
            return False
        candidate = hashlib.sha256((saltHex + providedKey).encode()).hexdigest()
        return hmac.compare_digest(candidate, digest)
    except (TypeError, ValueError):
        return False


async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader), db: Session = Depends(getStocksSession)):
    if not Config.STOCKS_API.KEY_SYSTEM:
        return None

    if not apiKey:
        raise HTTPException(status_code=401, detail="Unauthorized")

    try:
        # ponytail: full-table scan, move to server-side salted lookup if keys table grows large
        rows = db.query(StocksAPIKey).all()
        matchedPk = None
        exhaustedMatch = False
        for row in rows:
            if isValidStoredKey(apiKey, row.apiKey):
                if row.currentUsage < row.requestLimit:
                    matchedPk = row.apiKey
                    break
                exhaustedMatch = True

        if matchedPk is None:
            if exhaustedMatch:
                raise HTTPException(status_code=429, detail="Too many requests")
            raise HTTPException(status_code=401, detail="Unauthorized")

        result = db.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == matchedPk)
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        db.commit()

        if cast(CursorResult, result).rowcount == 0:
            raise HTTPException(status_code=429, detail="Too many requests")

        return apiKey

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="API key verification failed")
