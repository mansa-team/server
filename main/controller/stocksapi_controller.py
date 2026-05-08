import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from config import getSession

from main.app.stocks_api.query import stocksQuery
from main.app.stocks_api.key import verifyAPIKey, createKey
from main.app.user.user import UserManager
from main.utils.roles import Permission, Roles

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/stocks", tags=["Stocks API"])


@router.get("/health")
def health():
    return {"status": "ok", "service": "stocksapi"}


@router.get("/key")
def apiKeyTest(apiKey: str = Depends(verifyAPIKey)):
    return {"message": "API", "secured": True}


@router.get("/historical")
def getHistorical(
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=200, pattern=r"^[A-Z0-9,\s]*$"),
    dates: str = Query(None, max_length=50),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    apiKey: str = Depends(verifyAPIKey),
):
    return stocksQuery.queryHistorical(search, fields, dates, orderBy, limit)


@router.get("/fundamental")
def getFundamental(
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=200, pattern=r"^[A-Z0-9,\s]*$"),
    dates: str = Query(None, max_length=50),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    apiKey: str = Depends(verifyAPIKey),
):
    return stocksQuery.queryFundamental(search, fields, dates, orderBy, limit)


@router.get("/key/generate")
def generateKey(currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)):
    if not Roles.checkAccess(currentUser.get("roles", []), Permission.GENERATE_API_KEYS):
        raise HTTPException(
            status_code=403, detail="You do not have permission to generate API keys. Update to a Developer account."
        )

    try:
        userId = currentUser.get("userId")
        newKey = createKey(db, userId)
        return {"message": "Key successfully generated", "apiKey": newKey, "owner": currentUser.get("username")}
    except Exception as e:
        logger.error("Failed to generate API key", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate API key")
