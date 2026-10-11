"""Single-client OAuth authorization server (SoloAS) for the wallet MCP surface.

FastMCP-native subclass of ``fastmcp.server.auth.OAuthProvider``: no hand-rolled
/authorize or /token endpoints (those come free once attached to ``walletMcp``).
Closed for first-party testing: one static client (``opencode``), no DCR, PKCE-S256
enforced by the SDK's authorization handler, scope ``wallet`` only.

Source-verified against installed fastmcp 4.1.0 / mcp SDK:
- ``OAuthProvider`` lives in ``fastmcp.server.auth.auth`` (re-exported from
  ``fastmcp.server.auth``); there is NO ``fastmcp.server.auth.providers.oauth``.
- Abstract hooks come from ``mcp.server.auth.provider.OAuthAuthorizationServerProvider``:
  get_client / register_client / authorize / load_authorization_code /
  exchange_authorization_code / load_refresh_token / exchange_refresh_token /
  load_access_token / revoke_token. ``exchange_identity_assertion`` has a default
  (rejects jwt-bearer) and ``verify_token`` / ``scopes_supported`` are concrete.
- The SDK ``TokenHandler`` already enforces: client_secret (401 invalid_client),
  code expiry + redirect_uri match + PKCE-S256 (invalid_grant), refresh
  expiry and scope subsets. Provider hooks only mint / rotate / look up.
- ``ClientRegistrationOptions.enabled`` and ``RevocationOptions.enabled`` both
  default False: /register stays absent (closed), /revoke needs explicit opt-in.
"""

from __future__ import annotations

import html
import secrets
import time
from datetime import timedelta
from urllib.parse import urlencode, urlparse

from fastmcp.server.auth import AccessToken, MultiAuth, OAuthProvider
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.settings import RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, RedirectResponse, Response

from config import Config, SessionLocal
from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.constants import COOKIE_NAME, COOKIE_PATH, COOKIE_SAMESITE
from main.app.authentication.session import SessionManager
from main.app.authentication.util import (
    _ServiceLoopbackBackend,
    _ServiceLoopbackHeadersMiddleware,
    createAccessToken,
    verifyAccessToken,
    walletAuth,
)

WALLET_SCOPE = "wallet"
CODE_TTL_SECONDS = 600
ACCESS_TTL_SECONDS = 3600
REFRESH_TTL_SECONDS = 30 * 24 * 3600

LOOPBACK_HOSTS = ("localhost", "127.0.0.1", "::1")

revokedAccessJtis: dict[str, float] = {}


def oauthBaseUrl() -> str:
    return f"http://{Config.USER.HOST}:{Config.USER.PORT}/wallet/mcp"


class LoopbackRedirectClient(OAuthClientInformationFull):
    """Static first-party client: any loopback redirect_uri is accepted.

    OpenCode's OAuth callback is a dynamic-port loopback server, so exact-match
    registration is impossible. Per RFC 8252 section 7.3 any port on loopback is
    acceptable for a native first-party client; non-loopback URIs fall through
    to the strict exact-match check (and fail: nothing is registered).
    """

    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            try:
                host = (urlparse(str(redirect_uri)).hostname or "").strip("[]").lower()
            except Exception:
                host = ""
            if host in LOOPBACK_HOSTS:
                return redirect_uri
        return super().validate_redirect_uri(redirect_uri)


class SoloOAuthProvider(OAuthProvider):
    """Closed single-client AS: static ``opencode`` client, dict stores, HS256."""

    def __init__(self) -> None:
        super().__init__(
            base_url=oauthBaseUrl(),
            required_scopes=[WALLET_SCOPE],
            revocation_options=RevocationOptions(enabled=True),
        )
        self.codes: dict[str, AuthorizationCode] = {}
        self.codeSessions: dict[str, str] = {}
        self.refreshTokens: dict[str, RefreshToken] = {}
        self.refreshSessions: dict[str, str] = {}
        self.pending: dict[str, dict] = {}

    def clear(self) -> None:
        self.codes.clear()
        self.codeSessions.clear()
        self.refreshTokens.clear()
        self.refreshSessions.clear()
        self.pending.clear()

    def build_client(self) -> OAuthClientInformationFull | None:
        clientId = Config.USER.MCP_OAUTH_CLIENT_ID
        secret = Config.USER.MCP_OAUTH_CLIENT_SECRET
        if not clientId or not secret:
            return None
        return LoopbackRedirectClient(
            client_id=clientId,
            client_secret=secret,
            token_endpoint_auth_method="client_secret_post",
            grant_types=["authorization_code", "refresh_token"],
            scope=WALLET_SCOPE,
        )

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        client = self.build_client()
        if client is not None and client_id == client.client_id:
            return client
        return None

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        raise RuntimeError("client registration closed: single static client only")

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        # Fail closed on PKCE: installed AuthorizationParams carries only
        # code_challenge (no method field; the SDK wire type validates
        # code_challenge_method == S256 before we are reached). Direct calls
        # bypass the wire, so reject here on absent/empty challenge or on a
        # non-S256 method if one is ever forwarded.
        if not getattr(params, "code_challenge", None) or getattr(params, "code_challenge_method", "S256") != "S256":
            raise AuthorizeError("invalid_request", "PKCE S256 code_challenge required")
        scopes = params.scopes or [WALLET_SCOPE]
        for scope in scopes:
            if scope != WALLET_SCOPE:
                raise AuthorizeError("invalid_scope", f"unsupported scope {scope}")
        requestId = secrets.token_urlsafe(16)
        self.pending[requestId] = {
            "client_id": client.client_id,
            "scopes": scopes,
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_provided": params.redirect_uri_provided_explicitly,
            "resource": params.resource,
            "state": params.state,
            "expires_at": time.time() + CODE_TTL_SECONDS,
        }
        return f"{str(self.base_url).rstrip('/')}/oauth/login?request_id={requestId}"

    def take_pending(self, request_id: str) -> dict | None:
        item = self.pending.pop(request_id, None)
        if not item or item["expires_at"] < time.time():
            return None
        return item

    def peek_pending(self, request_id: str) -> dict | None:
        item = self.pending.get(request_id)
        if not item or item["expires_at"] < time.time():
            self.pending.pop(request_id, None)
            return None
        return item

    def issue_code(
        self,
        client_id: str,
        user_id: str,
        session_id: str,
        code_challenge: str,
        redirect_uri: str,
        redirect_provided: bool,
        scopes: list[str],
        resource: str | None,
    ) -> str:
        code = secrets.token_urlsafe(32)
        self.codes[code] = AuthorizationCode(
            code=code,
            scopes=scopes,
            expires_at=time.time() + CODE_TTL_SECONDS,
            client_id=client_id,
            code_challenge=code_challenge,
            redirect_uri=AnyUrl(redirect_uri),
            redirect_uri_provided_explicitly=redirect_provided,
            resource=resource,
            subject=str(user_id),
        )
        self.codeSessions[code] = str(session_id)
        return code

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.codes.get(authorization_code)
        if not code or code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        stored = self.codes.pop(authorization_code.code, None)
        sessionId = self.codeSessions.pop(authorization_code.code, "")
        if not stored:
            raise TokenError("invalid_grant", "authorization code does not exist")
        if stored.expires_at < time.time():
            raise TokenError("invalid_grant", "authorization code has expired")
        return self._mint(client.client_id, str(stored.subject or ""), sessionId, stored.scopes, stored.resource)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        stored = self.refreshTokens.get(refresh_token)
        if not stored or stored.client_id != client.client_id:
            return None
        return stored

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        stored = self.refreshTokens.pop(refresh_token.token, None)
        sessionId = self.refreshSessions.pop(refresh_token.token, "")
        if not stored:
            raise TokenError("invalid_grant", "refresh token does not exist")
        if stored.expires_at is not None and stored.expires_at < time.time():
            raise TokenError("invalid_grant", "refresh token has expired")
        return self._mint(
            client.client_id, str(stored.subject or ""), sessionId, scopes or stored.scopes, stored.resource
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            payload = verifyAccessToken(token)
        except Exception:
            return None
        if str(payload.get("jti") or "") in revokedAccessJtis:
            return None
        userIdRaw = payload.get("userId")
        sessionId = payload.get("sessionId")
        if userIdRaw is None or not sessionId:
            return None
        try:
            userId = int(userIdRaw)
        except (TypeError, ValueError):
            return None
        db = SessionLocal()
        try:
            valid = SessionManager.validateSession(db, str(sessionId), userId)
        except Exception:
            return None
        finally:
            db.close()
        if not valid:
            return None
        scopeRaw = payload.get("scope") or ""
        scopes = scopeRaw.split() if isinstance(scopeRaw, str) and scopeRaw else [WALLET_SCOPE]
        resource = payload.get("aud")
        exp = payload.get("exp")
        return AccessToken(
            token=token,
            client_id=str(payload.get("client_id") or ""),
            scopes=scopes,
            expires_at=int(exp) if isinstance(exp, (int, float)) else None,
            resource=str(resource) if resource else None,
            subject=str(userIdRaw),
        )

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        value = getattr(token, "token", "")
        if not value:
            return
        if value in self.refreshTokens:
            self.refreshTokens.pop(value, None)
            self.refreshSessions.pop(value, None)
            return
        try:
            payload = verifyAccessToken(value)
        except Exception:
            return
        jti = str(payload.get("jti") or "")
        if jti:
            now = time.time()
            cutoff = now - ACCESS_TTL_SECONDS
            for oldJti, seenAt in list(revokedAccessJtis.items()):
                if seenAt < cutoff:
                    del revokedAccessJtis[oldJti]
            revokedAccessJtis[jti] = now
        # The access token IS the session JWT: revoking it must end the grant,
        # otherwise the loopback verifier + per-tool identity would still honor
        # the same credential. Best-effort session revoke (logout semantics).
        userId, sessionId = payload.get("userId"), payload.get("sessionId")
        if userId is None or not sessionId:
            return
        try:
            userIdInt = int(userId)
        except (TypeError, ValueError):
            return
        db = SessionLocal()
        try:
            SessionManager.revokeSession(db, str(sessionId), userIdInt)
        except Exception:
            pass
        finally:
            db.close()

    def _mint(
        self, client_id: str, user_id: str, session_id: str, scopes: list[str], resource: str | None
    ) -> OAuthToken:
        useScopes = scopes or [WALLET_SCOPE]
        aud = resource or oauthBaseUrl()
        access = createAccessToken(
            {
                "userId": user_id,
                "sessionId": str(session_id),
                "client_id": client_id,
                "aud": aud,
                "scope": " ".join(useScopes),
                "jti": secrets.token_urlsafe(16),
            },
            expiresDelta=timedelta(seconds=ACCESS_TTL_SECONDS),
        )
        refreshValue = secrets.token_urlsafe(32)
        self.refreshTokens[refreshValue] = RefreshToken(
            token=refreshValue,
            client_id=client_id,
            scopes=useScopes,
            expires_at=int(time.time()) + REFRESH_TTL_SECONDS,
            resource=aud,
            subject=user_id,
        )
        self.refreshSessions[refreshValue] = str(session_id)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL_SECONDS,
            scope=" ".join(useScopes),
            refresh_token=refreshValue,
        )


class SoloAuth(MultiAuth):
    """SoloAS + loopback composition that preserves the service-token transport.

    MultiAuth's default middleware is Bearer-only: without the loopback
    presence shim and service-token backend, pool traffic carrying only
    X-Service-Token 401s before any verifier runs.
    """

    def get_middleware(self) -> list:
        return [
            Middleware(_ServiceLoopbackHeadersMiddleware),
            Middleware(AuthenticationMiddleware, backend=_ServiceLoopbackBackend(self)),  # type: ignore[arg-type]
            Middleware(AuthContextMiddleware),  # type: ignore[arg-type]
        ]


soloProvider = SoloOAuthProvider()

# Transport gate: SoloAS first, service-loopback second. required_scopes is
# empty so loopback credentials (plain session JWTs / service tokens, which
# carry no scope claim) keep working for the pool; "wallet only" is enforced
# at authorize time and minted into OAuth tokens.
soloAuth = SoloAuth(server=soloProvider, verifiers={"service-loopback": walletAuth}, required_scopes=[])


def _login_page(request_id: str, error: str | None) -> HTMLResponse:
    safeId = html.escape(request_id, quote=True)
    complaint = f"<p>{html.escape(error)}</p>" if error else ""
    return HTMLResponse(
        "<!doctype html><html><body>"
        "<h1>Mansa Wallet</h1>"
        f"{complaint}"
        '<form method="post">'
        f'<input type="hidden" name="request_id" value="{safeId}">'
        '<label>user <input name="username"></label>'
        '<label>password <input type="password" name="password"></label>'
        '<button type="submit">continue</button>'
        "</form></body></html>"
    )


def _session_from_cookie(request: Request, db) -> tuple[str, str] | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        payload = verifyAccessToken(raw)
    except Exception:
        return None
    userId, sessionId = payload.get("userId"), payload.get("sessionId")
    if userId is None or not sessionId:
        return None
    try:
        userIdInt = int(userId)
    except (TypeError, ValueError):
        return None
    try:
        valid = SessionManager.validateSession(db, str(sessionId), userIdInt)
    except Exception:
        return None
    if not valid:
        return None
    return str(userId), str(sessionId)


def register_login_routes(mcp) -> None:
    """Authorize-time browser routes: session cookie resumes, else inline login."""

    @mcp.custom_route("/oauth/login", methods=["GET", "POST"])
    async def oauth_login(request: Request) -> Response:
        form = await request.form() if request.method == "POST" else {}
        requestId = request.query_params.get("request_id") or (form.get("request_id") if form else None)
        if not isinstance(requestId, str) or not requestId:
            return HTMLResponse("missing request", status_code=400)
        pending = soloProvider.peek_pending(requestId)
        if not pending:
            return HTMLResponse("expired request", status_code=400)

        db = SessionLocal()
        try:
            identity: tuple[str, str] | None = _session_from_cookie(request, db)
            resume = False
            freshToken: str | None = None
            if identity is None and request.method == "POST":
                username = form.get("username")
                password = form.get("password")
                user = None
                if isinstance(username, str) and isinstance(password, str):
                    user = AuthenticationManager.authenticateUser(db, username, password)
                if not user:
                    return _login_page(requestId, "invalid credentials")
                session = SessionManager.createSession(db, int(user["userId"]), request.headers.get("User-Agent", ""))
                freshToken = createAccessToken({"userId": str(user["userId"]), "sessionId": session.sessionId})
                identity = (str(user["userId"]), str(session.sessionId))
                resume = True
            elif identity is None:
                return _login_page(requestId, None)

            live = soloProvider.take_pending(requestId)
            if not live:
                return HTMLResponse("expired request", status_code=400)
            code = soloProvider.issue_code(
                live["client_id"],
                identity[0],
                identity[1],
                live["code_challenge"],
                live["redirect_uri"],
                live["redirect_provided"],
                live["scopes"],
                live["resource"] or oauthBaseUrl(),
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
