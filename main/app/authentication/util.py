import hmac
import logging
import secrets
from urllib.parse import urlparse

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
import bcrypt
from fastmcp.server.auth import AccessToken
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser, BearerAuthBackend
from starlette.authentication import AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from config import SessionLocal
from main.app.authentication.constants import (
    COOKIE_NAME,
    COOKIE_PATH,
    COOKIE_SAMESITE,
    WALLET_RESOURCE_PATH,
    WALLET_SCOPE,
)
from main.app.authentication.service_token import verifyServiceToken
from main.app.authentication.tokens import createAccessToken, verifyAccessToken

logger = logging.getLogger(__name__)

MAX_PASSWORD_BYTES = 72

CSRF_COOKIE_NAME = "mansa_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def passwordExceedsByteLimit(password: str) -> bool:
    return len(password.encode("utf-8")) > MAX_PASSWORD_BYTES


def hashPassword(password: str):
    if not password:
        raise ValueError("Password cannot be empty")
    pwdBytes = password.encode("utf-8")
    hashed = bcrypt.hashpw(pwdBytes, bcrypt.gensalt())
    return hashed.decode("utf-8")


def verifyPassword(plainPassword: str | None, hashedPassword: str | None) -> bool:
    if not plainPassword or not hashedPassword:
        return False
    if passwordExceedsByteLimit(plainPassword):
        return False
    try:
        return bcrypt.checkpw(plainPassword.encode("utf-8"), hashedPassword.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def extractRawToken(request: Request) -> str | None:
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ", 1)[1]

    if not token:
        token = request.cookies.get(COOKIE_NAME)

    return token


def extractTokenPayload(request: Request) -> dict:
    token = extractRawToken(request)

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

    aud = payload.get("aud")
    if aud is not None:
        try:
            path = urlparse(str(aud)).path.rstrip("/")
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid audience")
        if not path.endswith(WALLET_RESOURCE_PATH):
            raise HTTPException(status_code=401, detail="Invalid audience")
    scope = payload.get("scope") if payload.get("scope") is not None else payload.get("scp")
    if scope is not None:
        parts = scope.split() if isinstance(scope, str) else list(scope)
        if WALLET_SCOPE not in parts:
            raise HTTPException(status_code=401, detail="Insufficient scope")

    return payload


def loopbackMiddleware(receiver) -> list:
    return [
        Middleware(ServiceLoopbackHeadersMiddleware),
        Middleware(AuthenticationMiddleware, backend=ServiceLoopbackBackend(receiver)),  # type: ignore[arg-type]
        Middleware(AuthContextMiddleware),  # type: ignore[arg-type]
    ]


def csrfExempt(endpoint):
    endpoint._csrf_exempt = True
    return endpoint


csrf_exempt = csrfExempt  # legacy name kept for existing importers


def isCsrfExemptEndpoint(request: Request) -> bool:
    route = request.scope.get("route")
    endpoint = getattr(route, "endpoint", None)
    if endpoint is None:
        endpoint = request.scope.get("endpoint")
    return bool(getattr(endpoint, "_csrf_exempt", False))


def issueCsrfToken(response: Response, request=None, token: str | None = None) -> str:
    token = token or secrets.token_urlsafe(32)
    response.set_cookie(
        key=CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        secure=True,
        samesite=COOKIE_SAMESITE,
        path=COOKIE_PATH,
    )
    return token


def validateCsrf(request: Request, sessionCookieName: str) -> None:
    if request.method not in MUTATING_METHODS:
        return
    if isCsrfExemptEndpoint(request):
        return
    if not request.cookies.get(sessionCookieName):
        return

    expected = request.cookies.get(CSRF_COOKIE_NAME, "")
    provided = request.headers.get(CSRF_HEADER_NAME, "") or request.headers.get("X-CSRFToken", "")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")


class ServiceLoopbackBackend(BearerAuthBackend):
    async def authenticate(self, conn: HTTPConnection) -> tuple | None:
        serviceToken = conn.headers.get("x-service-token", "")
        if serviceToken:
            try:
                session = SessionLocal()
                try:
                    valid = verifyServiceToken(session, serviceToken)
                finally:
                    session.close()
            except Exception:
                valid = False
            if valid:
                return AuthCredentials([]), AuthenticatedUser(
                    AccessToken(token=serviceToken, client_id="service-loopback", scopes=[])
                )
        return await super().authenticate(conn)


class ServiceLoopbackHeadersMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            names = {name.lower() for name, _value in scope.get("headers", [])}
            if b"x-service-token" in names and b"authorization" not in names:
                scope["headers"] = [
                    *scope.get("headers", []),
                    (b"authorization", f"Bearer {'service-loopback'}".encode()),
                ]
        await self.app(scope, receive, send)


class CsrfProtectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            validateCsrf(request, COOKIE_NAME)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)
