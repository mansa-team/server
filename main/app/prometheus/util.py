from imports import *
from fastapi import HTTPException, Depends
from fastapi.security import APIKeyHeader

apiKeyHeader = APIKeyHeader(name="X-API-Key", auto_error=False)
async def verifyAPIKey(apiKey: str = Depends(apiKeyHeader)):
    if Config.PROMETHEUS['KEY.SYSTEM'] == 'FALSE':
        return None
    
    validKey = Config.PROMETHEUS['KEY']
    if not validKey:
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if apiKey is None or apiKey != validKey:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    return apiKey