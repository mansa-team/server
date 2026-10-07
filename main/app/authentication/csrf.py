import hmac
import logging
import secrets

from fastapi import HTTPException, Request, Response

from main.app.authentication.constants import COOKIE_PATH, COOKIE_SAMESITE

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


def issueCsrfToken(response: Response, request=None) -> str:
    token = secrets.token_urlsafe(32)
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
