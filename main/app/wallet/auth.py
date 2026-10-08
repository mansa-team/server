"""Wallet auth verifier behind the auth introspect seam.

Only auth touches sessions; wallet validates via POST /auth/introspect
with X-Service-Token. Base URL comes from Config.USER.HOST/PORT so the
auth/wallet split is config-only (same USER deployable today, localhost
default keeps co-located working).
"""

import logging

import httpx
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from config import Config, getSession
from main.app.authentication.constants import COOKIE_NAME

logger = logging.getLogger(__name__)


def authServiceBaseUrl() -> str:
    return f"http://{Config.USER.HOST}:{Config.USER.PORT}"


def mintServiceToken(db: Session | None = None) -> str:
    from main.app.authentication import service_token as serviceTokens
    import inspect

    try:
        params = inspect.signature(serviceTokens.createServiceToken).parameters
    except (TypeError, ValueError):
        params = {}  # type: ignore[assignment]
    if "db" in params:
        if db is None:
            raise ValueError("service token mint requires db")
        return serviceTokens.createServiceToken(db)
    return serviceTokens.createServiceToken()  # type: ignore[call-arg]


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
    try:
        serviceToken = mintServiceToken(db)
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")
    url = f"{authServiceBaseUrl()}/auth/introspect"
    try:
        resp = httpx.post(
            url,
            json={"token": raw},
            headers={"X-Service-Token": serviceToken},
            timeout=5.0,
        )
    except Exception as exc:
        logger.warning("wallet introspect call failed: %s", exc)
        raise HTTPException(status_code=401, detail="Unauthorized")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Unauthorized")
    try:
        payload = resp.json()
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not isinstance(payload, dict) or payload.get("userId") is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return payload
