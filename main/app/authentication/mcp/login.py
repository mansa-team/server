from __future__ import annotations

import hmac
import html
import secrets
from urllib.parse import urlencode, urlparse

from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from config import Config, SessionLocal
from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.constants import COOKIE_NAME, COOKIE_PATH, COOKIE_SAMESITE, WALLET_RESOURCE_PATH
from main.app.authentication.verifier import resourceUrl
from main.app.authentication.session import SessionManager
from main.app.authentication import verifier as appVerifier
from main.app.authentication.tokens import createAccessToken
from main.app.authentication.util import CSRF_COOKIE_NAME, CSRF_HEADER_NAME, issueCsrfToken


def oauthResumePath(requestId: str) -> str:
    basePath = urlparse(f"{Config.USER.MCP_PUBLIC_BASE_URL.rstrip('/')}{WALLET_RESOURCE_PATH}").path.rstrip("/")
    return f"{basePath}/oauth/login?{urlencode({'request_id': requestId})}"


def loginPage(requestId: str, error: str | None) -> HTMLResponse:
    safeId = html.escape(requestId, quote=True)
    complaint = f"<p>{html.escape(error)}</p>" if error else ""
    googleHref = f"/auth/google?{urlencode({'redirect_url': oauthResumePath(requestId)})}"
    safeGoogle = html.escape(googleHref, quote=True)
    csrfToken = secrets.token_urlsafe(32)
    response = HTMLResponse(
        "<!doctype html><html><body>"
        "<h1>Mansa Wallet</h1>"
        f"{complaint}"
        '<form method="post">'
        f'<input type="hidden" name="request_id" value="{safeId}">'
        f'<input type="hidden" name="csrf_token" value="{csrfToken}">'
        '<label>user <input name="username"></label>'
        '<label>password <input type="password" name="password"></label>'
        '<button type="submit">continue</button>'
        "</form>"
        f'<p><a href="{safeGoogle}">Continue with Google</a></p></body></html>'
    )
    issueCsrfToken(response, token=csrfToken)
    return response


def sessionFromCookie(request: Request, db) -> tuple[str, str] | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    identity = appVerifier.resolveSessionIdentity(db, raw)
    if identity is None:
        return None
    return str(identity[0]), str(identity[1])


def registerLoginRoutes(mcp, provider) -> None:
    @mcp.custom_route("/oauth/login", methods=["GET", "POST"])
    async def oauthLogin(request: Request) -> Response:
        form = await request.form() if request.method == "POST" else {}
        if request.method == "POST":
            expected = request.cookies.get(CSRF_COOKIE_NAME, "")
            provided = form.get("csrf_token") or request.headers.get(CSRF_HEADER_NAME, "")
            if not expected or not provided or not hmac.compare_digest(str(provided), expected):
                return HTMLResponse("csrf token missing or invalid", status_code=403)
        requestId = request.query_params.get("request_id") or (form.get("request_id") if form else None)
        if not isinstance(requestId, str) or not requestId:
            return HTMLResponse("missing request", status_code=400)
        pending = provider.peek_pending(requestId)
        if not pending:
            return HTMLResponse("expired request", status_code=400)

        db = SessionLocal()
        try:
            identity: tuple[str, str] | None = sessionFromCookie(request, db)
            resume = False
            freshToken: str | None = None
            if identity is None and request.method == "POST":
                username = form.get("username")
                password = form.get("password")
                user = None
                if isinstance(username, str) and isinstance(password, str):
                    user = AuthenticationManager.authenticateUser(db, username, password)
                if not user:
                    return loginPage(requestId, "invalid credentials")
                session = SessionManager.createSession(db, int(user["userId"]), request.headers.get("User-Agent", ""))
                freshToken = createAccessToken({"userId": str(user["userId"]), "sessionId": session.sessionId})
                identity = (str(user["userId"]), str(session.sessionId))
                resume = True
            elif identity is None:
                return loginPage(requestId, None)

            live = provider.take_pending(requestId)
            if not live:
                return HTMLResponse("expired request", status_code=400)
            code = provider.issue_code(
                live["client_id"],
                identity[0],
                identity[1],
                live["code_challenge"],
                live["redirect_uri"],
                live["redirect_provided"],
                live["scopes"],
                live["resource"] or resourceUrl(),
            )
            params = {"code": code}
            if live["state"]:
                params["state"] = live["state"]
            sep = "&" if urlparse(live["redirect_uri"]).query else "?"
            response = RedirectResponse(f"{live['redirect_uri']}{sep}{urlencode(params)}", status_code=302)
            if resume and freshToken:
                response.set_cookie(
                    key=COOKIE_NAME,
                    value=freshToken,
                    httponly=True,
                    secure=True,
                    samesite=COOKIE_SAMESITE,
                    path=COOKIE_PATH,
                )
            return response
        finally:
            db.close()
