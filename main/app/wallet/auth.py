import logging

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import getSession
from main.app.authentication.introspect import introspectToken
from main.utils.roles import Permission, Roles

logger = logging.getLogger(__name__)


def resolveRawToken(request: Request) -> str:
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]
    if not token:
        token = request.cookies.get("mansa_token")
    if not token:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return token


def getWalletIdentity(request: Request, db: Session = Depends(getSession)) -> dict:
    return introspectToken(db, resolveRawToken(request))


def requireWalletUser(identity: dict = Depends(getWalletIdentity)) -> dict:
    if not Roles.checkAccess(identity.get("roles", []), Permission.WALLET):
        raise HTTPException(status_code=403, detail="Missing required permission: WALLET")
    return identity


def requireWalletOwnership(walletUserId: int, identity: dict) -> None:
    if walletUserId != identity["userId"]:
        raise HTTPException(status_code=403, detail="not-owner")
