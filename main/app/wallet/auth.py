from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import getSession
from main.app.authentication.constants import COOKIE_NAME
from main.app.authentication.introspect import introspectToken


def extractWalletToken(request: Request) -> str | None:
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]
    if not token:
        token = request.cookies.get(COOKIE_NAME)
    return token


def getWalletUser(request: Request, db: Session = Depends(getSession)) -> dict:
    raw = extractWalletToken(request)
    if not raw:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return introspectToken(db, raw)
