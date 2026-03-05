from config import Config, SessionLocal

from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader

import secrets
import string

from main.models import StocksAPIKey

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)

async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader)):
    if Config.STOCKS_API['KEY.SYSTEM'] == 'FALSE':
        return None
    
    if not apiKey:
        raise HTTPException(status_code=401, detail="Missing API key")

    db = SessionLocal()
    try:
        stocksKey = db.query(StocksAPIKey).filter(StocksAPIKey.apiKey == apiKey).first()
        
        if not stocksKey:
            if apiKey == Config.STOCKS_API['KEY']:
                return apiKey
            raise HTTPException(status_code=401, detail="Invalid API key")

        resetDays = int(Config.STOCKS_API['QUOTA.RESETDAYS'])
        if stocksKey.needsReset(resetDays):
            stocksKey.resetQuota()
            db.commit()

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
    finally:
        db.close()

def generateSecureKey(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def createKey(userId: int):
    newKey = generateSecureKey(32)
    quota = int(Config.STOCKS_API['DEFAULT.QUOTA'])
    
    db = SessionLocal()
    try:
        existingKey = db.query(StocksAPIKey).filter(StocksAPIKey.userId == userId).first()
        
        if existingKey:
            existingKey.apiKey = newKey
            existingKey.requestLimit = quota
        else:
            newKeyObj = StocksAPIKey(
                apiKey=newKey,
                userId=userId,
                requestLimit=quota,
                currentUsage=0
            )
            db.add(newKeyObj)
        
        db.commit()
        return newKey
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to create API key")
    finally:
        db.close()