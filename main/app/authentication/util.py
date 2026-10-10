import logging
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
from fastmcp.server.auth import AccessToken, JWTVerifier
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from mcp.server.auth.middleware.bearer_auth import AuthenticatedUser, BearerAuthBackend
from starlette.authentication import AuthCredentials
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Receive, Scope, Send

from config import Config, SessionLocal
from main.app.authentication.constants import TOKEN_EXPIRY_HOURS, COOKIE_NAME
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

    return payload


class _ServiceLoopbackBackend(BearerAuthBackend):
    """X-Service-Token (opaque service session row) OR Bearer user JWT.

    Header read + DB check per request, never import-time. A valid service
    token authenticates the pool's transport connection but resolves NO user:
    per-tool `authorization` args stay the sole identity (an opaque service
    token never decodes as a user JWT, so it 401s at the tool layer).
    """

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


_SERVICE_LOOPBACK_MARKER = "service-loopback"


class _ServiceLoopbackHeadersMiddleware:
    """Presence shim for FastMCP's Bearer gate (RequireAuthMiddleware 401s with
    no Authorization header before the auth backend ever runs).

    When X-Service-Token rides without Authorization, injects a marker Bearer
    so the request reaches the backend, which authenticates via X-Service-Token
    (DB check) and never verifies the marker. Forged service tokens still 401
    (invalid_token) at the backend; requests with neither header keep the
    missing-auth 401.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            names = {name.lower() for name, _value in scope.get("headers", [])}
            if b"x-service-token" in names and b"authorization" not in names:
                scope["headers"] = [
                    *scope.get("headers", []),
                    (b"authorization", f"Bearer {_SERVICE_LOOPBACK_MARKER}".encode()),
                ]
        await self.app(scope, receive, send)


class ServiceLoopbackVerifier(JWTVerifier):
    """User session JWTs plus the service-loopback credential on one transport."""

    def get_middleware(self) -> list:
        return [
            Middleware(_ServiceLoopbackHeadersMiddleware),
            Middleware(AuthenticationMiddleware, backend=_ServiceLoopbackBackend(self)),  # type: ignore[arg-type]
            Middleware(AuthContextMiddleware),  # type: ignore[arg-type]
        ]


walletAuth = ServiceLoopbackVerifier(
    public_key=Config.USER.JWT_SECRET_KEY,
    algorithm="HS256",
)
