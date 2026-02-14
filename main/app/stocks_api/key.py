from imports import *

import secrets
import string

APIKey_Header = APIKeyHeader(name="X-API-Key", auto_error=False)
async def verifyAPIKey(APIKey: str = Depends(APIKey_Header)):
    if Config.STOCKS_API['KEY.SYSTEM'] == 'FALSE':
        return None
    
    if not APIKey:
        raise HTTPException(status_code=401, detail="Missing API key")

    with dbEngine.begin() as conn:
        query = text("""
            SELECT requestLimit, currentUsage, lastReset 
            FROM stocksapi_keys WHERE apiKey = :key
        """)
        row = conn.execute(query, {"key": APIKey}).fetchone()
        
        if not row:
            if APIKey == Config.STOCKS_API['KEY']:
                return APIKey
            raise HTTPException(status_code=401, detail="Invalid API key")

        limit, usage, lastReset = row
        daysSinceReset = (datetime.now() - lastReset).days

        if daysSinceReset >= Config.STOCKS_API['QUOTA.RESETDAYS']:
            usage = 0
            conn.execute(text("UPDATE stocksapi_keys SET currentUsage = 0, lastReset = CURRENT_TIMESTAMP WHERE apiKey = :key"), {"key": APIKey})
        
        if usage >= limit:
            raise HTTPException(status_code=429, detail="quota exceeded")

        conn.execute(text("UPDATE stocksapi_keys SET currentUsage = currentUsage + 1 WHERE apiKey = :key"), {"key": APIKey})
    return APIKey

def generateSecureKey(length=32):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

def createKey(userId: int):
    newKey = generateSecureKey(32)
    quota = Config.STOCKS_API['DEFAULT.QUOTA']
    
    with dbEngine.begin() as conn:
        existing = conn.execute(
            text("SELECT currentUsage FROM stocksapi_keys WHERE userId = :uid"),
            {"uid": userId}
        ).fetchone()
        
        if existing:
            conn.execute(
                text("""
                    UPDATE stocksapi_keys 
                    SET apiKey = :key, requestLimit = :lim 
                    WHERE userId = :uid
                """),
                {"key": newKey, "lim": quota, "uid": userId}
            )
            usage = existing[0]
        else:
            conn.execute(
                text("""
                    INSERT INTO stocksapi_keys (apiKey, userId, requestLimit, currentUsage) 
                    VALUES (:key, :uid, :lim, 0)
                """),
                {"key": newKey, "uid": userId, "lim": quota}
            )

    return newKey