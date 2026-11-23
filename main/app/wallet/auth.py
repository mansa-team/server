from fastapi import Depends, Request
from sqlalchemy.orm import Session

from config import getSession
from main.app.authentication.util import extractRawToken
from main.app.authentication.verifier import verifyWalletUser


def getWalletUser(request: Request, db: Session = Depends(getSession)) -> dict:
    return verifyWalletUser(db, extractRawToken(request))
