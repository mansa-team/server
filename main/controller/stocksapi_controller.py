import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
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


@router.get("/historical")
def getHistorical(
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=200, pattern=r"^[A-Z0-9,\s]*$"),
    dates: str = Query(None, max_length=21),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    apiKey: str = Depends(verifyAPIKey),
):
    result = stocksQuery.queryHistorical(search, fields, dates, orderBy, limit)
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/fundamental")
def getFundamental(
    search: str = Query(None, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    fields: str = Query(None, max_length=200, pattern=r"^[A-Z0-9,\s]*$"),
    dates: str = Query(None, max_length=21),
    orderBy: str = Query(None),
    limit: int = Query(None, ge=1, le=1000),
    apiKey: str = Depends(verifyAPIKey),
):
    result = stocksQuery.queryFundamental(search, fields, dates, orderBy, limit)
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/cotations")
def getCotations(
    search: str = Query(..., min_length=1, max_length=3780, pattern=r"^[A-Za-z0-9,\s]*$"),
    dates: str = Query(None, max_length=21),
    adjusted: bool = Query(False),
    apiKey: str = Depends(verifyAPIKey),
):
    result = stocksQuery.queryCotations(search, dates, adjusted)
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=300"})


@router.get("/cotations/live")
def getLiveCotation(
    search: str = Query(..., min_length=1, max_length=7, pattern=r"^[A-Za-z0-9,\s]*$"),
    apiKey: str = Depends(verifyAPIKey),
):
    result = stocksQuery.queryLiveCotation(search)
    return JSONResponse(content=result, headers={"Cache-Control": "public, max-age=15"})


@router.get("/key/generate")
def generateKey(currentUser: dict = Depends(UserManager.getCurrentUser), db: Session = Depends(getSession)):
    if not Roles.checkAccess(currentUser.get("roles", []), Permission.GENERATE_API_KEYS):
        raise HTTPException(
            status_code=403, detail="You do not have permission to generate API keys. Update to a Developer account."
        )

    userId = currentUser.get("userId")
    newKey = createKey(db, userId)
    return {"message": "Key successfully generated", "apiKey": newKey, "owner": currentUser.get("username")}
