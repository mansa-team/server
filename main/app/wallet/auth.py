from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import getSession
from main.app.authentication.introspect import introspectToken
from main.app.authentication.util import extractRawToken


def getWalletUser(request: Request, db: Session = Depends(getSession)) -> dict:
    raw = extractRawToken(request)
    if not raw:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return introspectToken(db, raw)
