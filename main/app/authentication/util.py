import logging
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, Request
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from sqlalchemy.orm import Session

from config import Config, getSession
from main.app.authentication.constants import TOKEN_EXPIRY_HOURS, COOKIE_NAME
from main.app.authentication.oauth_shared import RESOURCE_METADATA_URL, revokedAccessJtis
from main.app.authentication.service_token import verifyServiceToken

logger = logging.getLogger(__name__)


def hashPassword(password: str):
    if not password:
        raise ValueError("Password cannot be empty")
    pwdBytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pwdBytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verifyPassword(plainPassword: str | None, hashedPassword: str | None) -> bool:
    if not plainPassword or not hashedPassword:
        return False
    try:
        return bcrypt.checkpw(plainPassword.encode("utf-8"), hashedPassword.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def createAccessToken(data: dict | None, expiresDelta: timedelta | None = None):
    if data is None:
        data = {}
    if expiresDelta is None:
        expiresDelta = timedelta(hours=TOKEN_EXPIRY_HOURS)

    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expiresDelta

    token = jwt.encode(payload, Config.USER.JWT_SECRET_KEY, algorithm="HS256")
    return token


def verifyAccessToken(token: str) -> dict:
    try:
        # aud/scope are enforced manually by enforceResourceClaims (absent
        # claims pass for session back-compat), so skip PyJWT's aud check.
        payload = jwt.decode(token, Config.USER.JWT_SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def extractRawToken(request: Request) -> str | None:
    """Raw session token from the request: X-Access-Token -> Authorization Bearer -> cookie.

    Same source precedence as extractTokenPayload, but returns the raw string
    (extractTokenPayload returns only the decoded payload). Used to forward the
    caller's own session JWT to MCP-bound tool calls.
    """
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if not token:
        token = request.cookies.get(COOKIE_NAME)

    return token


def enforceResourceClaims(payload: dict) -> None:
    """Enforce aud/scope WHEN PRESENT; absent claims pass (session back-compat)."""
    aud = payload.get("aud")
    if aud is not None:
        try:
            path = urlparse(str(aud)).path.rstrip("/")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid audience")
        if not path.endswith("/wallet/mcp"):
            raise HTTPException(status_code=401, detail="Invalid audience")
    scope = payload.get("scope") if payload.get("scope") is not None else payload.get("scp")
    if scope is not None:
        parts = scope.split() if isinstance(scope, str) else list(scope)
        if "wallet" not in parts:
            raise HTTPException(status_code=401, detail="Insufficient scope")


def extractTokenPayload(request: Request) -> dict:
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if not token:
        token = request.cookies.get(COOKIE_NAME)
        logger.info(f"Cookie fallback: token={'FOUND' if token else 'NONE'}, cookies={list(request.cookies.keys())}")

    if not token:
        raise HTTPException(status_code=401, detail="Session not found")

    try:
        payload = verifyAccessToken(token)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid Token")

    if payload.get("userId") is None:
        raise HTTPException(status_code=401, detail="Invalid Token")

    enforceResourceClaims(payload)

    try:
        if payload.get("jti") and payload.get("jti") in revokedAccessJtis:
            raise HTTPException(status_code=401, detail="Token revoked")
    except HTTPException:
        raise
    except Exception:
        pass

    return payload


def verifyMcpTransport(request: Request, db: Session = Depends(getSession)):
    """Outer MCP challenge: service loopback OR user JWT, else 401+WWW-Authenticate.

    GET passes through so the mount probe stays 406 (MCP calls are POST).
    Service tokens (opaque X-Service-Token session rows) never resolve to a
    user wallet: inner getCurrentUser still requires a user JWT and rejects
    non-user sessions.
    """
    if request.method == "GET":
        return None

    if verifyServiceToken(db, request.headers.get("X-Service-Token", "")):
        return {"type": "service"}

    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]
    if not token:
        token = request.cookies.get(COOKIE_NAME)

    def challenge(detail: str):
        raise HTTPException(
            status_code=401,
            detail=detail,
            headers={
                "WWW-Authenticate": (
                    f'Bearer resource_metadata="{RESOURCE_METADATA_URL}", '
                    f'error="invalid_token", error_description="{detail}"'
                )
            },
        )

    if not token:
        challenge("Authentication required")
    assert token is not None
    if verifyServiceToken(db, token):
        return {"type": "service"}
    try:
        payload = verifyAccessToken(token)
    except HTTPException:
        challenge("Invalid token")
    try:
        enforceResourceClaims(payload)
    except HTTPException:
        challenge("Invalid token claims")
    try:
        if payload.get("jti") and payload.get("jti") in revokedAccessJtis:
            challenge("Token revoked")
    except HTTPException:
        raise
    except Exception:
        pass
    if payload.get("userId") is None or payload.get("sessionId") is None:
        challenge("Invalid token")
    return payload
