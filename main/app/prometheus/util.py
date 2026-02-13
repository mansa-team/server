from imports import *

APIKey_Header = APIKeyHeader(name="X-API-Key", auto_error=False)
async def verifyAPIKey(APIKey: str = Depends(APIKey_Header)):
    if Config.PROMETHEUS['KEY.SYSTEM'] == 'FALSE':
        return None
    
    validKey = Config.PROMETHEUS['KEY']
    if not validKey:
        raise HTTPException(status_code=500, detail="API key not configured")
    
    if APIKey is None or APIKey != validKey:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    return APIKey