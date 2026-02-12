from fastapi import APIRouter, Query, Depends
from main.app.stocks_api.query import queryFundamental, queryHistorical
from main.app.stocks_api.util import verifyAPIKey

router = APIRouter(
    prefix="/stocks",
    tags=["Stocks API"]
)

@router.get("/health")
async def health():
    return {"status": "ok", "service": "stocksapi"}

@router.get("/key")
async def apiKeyTest(api_key: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}

@router.get("/historical")
async def getHistorical(search: str = Query(None), fields: str = Query(None), dates: str = Query(None), api_key: str = Depends(verifyAPIKey)):
    return await queryHistorical(search, fields, dates)

@router.get("/fundamental")
async def getFundamental(search: str = Query(None), fields: str = Query(None), dates: str = Query(None), api_key: str = Depends(verifyAPIKey)):
    return await queryFundamental(search, fields, dates)