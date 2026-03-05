from fastapi import APIRouter, Depends, Query, HTTPException

from main.app.stocks_api.query import stocksQuery
from main.app.stocks_api.key import verifyAPIKey, createKey
from main.app.authentication.util import getCurrentUser
from main.utils.roles import Permission, Roles

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
    return stocksQuery.queryHistorical(search, fields, dates)

@router.get("/fundamental")
def getFundamental(search: str = Query(None), fields: str = Query(None), dates: str = Query(None), api_key: str = Depends(verifyAPIKey)):
    return stocksQuery.queryFundamental(search, fields, dates)

@router.get("/key/generate")
def generateKey(currentUser: dict = Depends(getCurrentUser)):
    if not Roles.checkAccess(currentUser.get("roles", []), Permission.GENERATE_API_KEYS):
        raise HTTPException(
            status_code=403, 
            detail="You do not have permission to generate API keys. Update to a Developer account."
        )

    try: 
        userId = currentUser.get("userId")
        newKey = createKey(userId)
        return {
            "message": "Key successfully generated", 
            "apiKey": newKey,
            "owner": currentUser.get("username")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
