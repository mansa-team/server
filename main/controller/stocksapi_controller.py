from fastapi import APIRouter, Depends, Query, HTTPException

from main.app.stocks_api.query import queryFundamental, queryHistorical
from main.app.stocks_api.key import verifyAPIKey, createKey

router = APIRouter(
    prefix="/stocks",
    tags=["Stocks API"]
)

@router.get("/health")
def health():
    return {"status": "ok", "service": "stocksapi"}

@router.get("/key")
def apiKeyTest(api_key: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}

@router.get("/historical")
def getHistorical(search: str = Query(None), fields: str = Query(None), dates: str = Query(None), api_key: str = Depends(verifyAPIKey)):
    return queryHistorical(search, fields, dates)

@router.get("/fundamental")
def getFundamental(search: str = Query(None), fields: str = Query(None), dates: str = Query(None), api_key: str = Depends(verifyAPIKey)):
    return queryFundamental(search, fields, dates)

@router.get("/key/generate")
def generateKey(userId: int = Query(None)):
    try: 
        newKey = createKey(userId)
        return {"message": "Key successfully generated", "apiKey": newKey}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
