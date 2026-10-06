"""Double-submit anti-CSRF for cookie-authenticated mutating routes.

Cookie `mansa_csrf` (readable by JS, Secure-always, SameSite=lax) holds a
random token. Mutating requests that carry the session cookie must echo it
back in the `X-CSRF-Token` header. Header-authenticated API calls
(X-Access-Token / Authorization: Bearer without the session cookie) are
exempt — they are not auto-sent by browsers so have no CSRF exposure.
"""

import hmac
import logging
import secrets

from fastapi import HTTPException, Request, Response

from main.app.authentication.constants import COOKIE_PATH, COOKIE_SAMESITE

logger = logging.getLogger(__name__)

CSRF_COOKIE_NAME = "mansa_csrf"
CSRF_HEADER_NAME = "x-csrf-token"

MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# No session exists yet (or service-to-service): nothing to forge.
CSRF_EXEMPT_PATHS = frozenset(
    {
        "/auth/login",
        "/auth/register",
        "/auth/google",
        "/auth/callback",
        "/auth/introspect",
        "/auth/csrf",
        "/auth/health",
        "/user/health",
        "/stocks/health",
        "/orunmila/health",
        "/health",
        "/status",
    }
)


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


def _authViaCookie(request: Request, sessionCookieName: str) -> bool:
    return bool(request.cookies.get(sessionCookieName))


def validateCsrf(request: Request, sessionCookieName: str) -> None:
    if request.method not in MUTATING_METHODS:
        return
    if request.url.path in CSRF_EXEMPT_PATHS:
        return
    if not _authViaCookie(request, sessionCookieName):
        return  # header-only API call — no cookie to forge
    expected = request.cookies.get(CSRF_COOKIE_NAME, "")
    provided = request.headers.get(CSRF_HEADER_NAME, "") or request.headers.get("X-CSRFToken", "")
    if not expected or not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid")
