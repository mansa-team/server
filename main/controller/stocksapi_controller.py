from fastapi import APIRouter, Depends, Query
from main.app.stocks_api.query import queryFundamental, queryHistorical
from main.app.stocks_api.util import verifyAPIKey

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