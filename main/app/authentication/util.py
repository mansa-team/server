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

MAX_PASSWORD_BYTES = 72


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
        payload = jwt.decode(token, Config.USER.JWT_SECRET_KEY, algorithms=["HS256"], options={"verify_aud": False})
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


def extractRawToken(request: Request) -> str | None:
    token = request.headers.get("X-Access-Token")
    if not token:
        authHeader = request.headers.get("Authorization")
        if authHeader and authHeader.startswith("Bearer "):
            token = authHeader.split(" ")[1]

    if not token:
        token = request.cookies.get(COOKIE_NAME)

    return token


def enforceResourceClaims(payload: dict) -> None:
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

    enforceResourceClaims(payload)

    return payload


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


class ServiceLoopbackVerifier(JWTVerifier):
    def get_middleware(self) -> list:
        return [
            Middleware(ServiceLoopbackHeadersMiddleware),
            Middleware(AuthenticationMiddleware, backend=ServiceLoopbackBackend(self)),  # type: ignore[arg-type]
            Middleware(AuthContextMiddleware),  # type: ignore[arg-type]
        ]


walletAuth = ServiceLoopbackVerifier(
    public_key=Config.USER.JWT_SECRET_KEY,
    algorithm="HS256",
)
