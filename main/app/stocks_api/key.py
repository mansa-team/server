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

UNAUTHORIZED_DETAIL = "Unauthorized"
QUOTA_DETAIL = "Too many requests"

SALT_BYTES = 16
_STORED_SEP = "$"


def hashApiKey(rawKey: str, saltHex: str) -> str:
    return hashlib.sha256((saltHex + rawKey).encode()).hexdigest()


def createStoredApiKey(rawKey: str | None = None) -> tuple[str, str]:
    raw = rawKey or secrets.token_urlsafe(32)
    saltHex = secrets.token_hex(SALT_BYTES)
    return raw, f"{saltHex}{_STORED_SEP}{hashApiKey(raw, saltHex)}"


def isValidStoredKey(providedKey: str, storedKey: str | None) -> bool:
    try:
        if not providedKey or not storedKey or _STORED_SEP not in storedKey:
            return False
        saltHex, digest = storedKey.split(_STORED_SEP, 1)
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
        raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

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
                raise HTTPException(status_code=429, detail=QUOTA_DETAIL)
            raise HTTPException(status_code=401, detail=UNAUTHORIZED_DETAIL)

        result = db.execute(
            update(StocksAPIKey)
            .where(StocksAPIKey.apiKey == matchedPk)
            .where(StocksAPIKey.currentUsage < StocksAPIKey.requestLimit)
            .values(currentUsage=StocksAPIKey.currentUsage + 1)
        )
        db.commit()

        if cast(CursorResult, result).rowcount == 0:
            raise HTTPException(status_code=429, detail=QUOTA_DETAIL)

        return apiKey

    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="API key verification failed")
