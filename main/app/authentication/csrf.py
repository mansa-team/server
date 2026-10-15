import hmac
import logging
import secrets

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from main.app.authentication.constants import COOKIE_NAME, COOKIE_PATH, COOKIE_SAMESITE

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "mansa_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def csrf_exempt(endpoint):
    endpoint._csrf_exempt = True
    return endpoint


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


class CsrfProtectMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            validateCsrf(request, COOKIE_NAME)
        except HTTPException as exc:
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        return await call_next(request)
