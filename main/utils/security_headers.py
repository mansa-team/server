import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

HSTS_VALUE = "max-age=31536000; includeSubDomains"


def getRequestScheme(request: Request) -> str:
    forwarded = ""
    try:
        forwarded = request.headers.get("x-forwarded-proto", "") or ""
    except Exception:
        forwarded = ""
    if isinstance(forwarded, str) and forwarded.strip():
        return forwarded.split(",")[0].strip().lower()
    try:
        scheme = request.url.scheme or ""
    except Exception:
        scheme = ""
    return scheme.lower() if isinstance(scheme, str) else ""


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        if getRequestScheme(request) == "https":
            response.headers.setdefault("Strict-Transport-Security", HSTS_VALUE)
        return response
