from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastmcp.server.auth import AccessToken, MultiAuth, OAuthProvider
from mcp.server.auth.provider import (
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
)
from mcp.server.auth.routes import cors_middleware
from mcp.server.auth.settings import RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl, AnyUrl
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from config import Config, LOCALHOST_ADDRESSES, SessionLocal
from main.app.authentication.constants import ACCESS_TTL, CODE_TTL, REFRESH_TTL, WALLET_RESOURCE_PATH, WALLET_SCOPE
from main.app.authentication.mcp.server import (
    CodeRecord,
    FastAPIStyleRequest,
    MansaAuthorizationServer,
    OAuthStore,
    OAuthUser,
    RefreshRecord,
    StaticClient,
)
from main.app.authentication.mcp.verifier import verifyMcpAccessToken
from main.app.authentication.session import SessionManager
from main.app.authentication.tokens import decodeToken
from main.app.authentication.util import loopbackMiddleware
from main.app.authentication.verifier import REVOKED_ACCESS_JTIS, resourceUrl

CODE_TTL_SECONDS = CODE_TTL
ACCESS_TTL_SECONDS = ACCESS_TTL
REFRESH_TTL_SECONDS = REFRESH_TTL

revokedJtiTimes: dict[str, float] = {}


class LoopbackRedirectClient(OAuthClientInformationFull):
    def validate_redirect_uri(self, redirect_uri: AnyUrl | None) -> AnyUrl:
        if redirect_uri is not None:
            try:
                host = (urlparse(str(redirect_uri)).hostname or "").strip("[]").lower()
            except Exception:
                host = ""
            if host in LOCALHOST_ADDRESSES:
                return redirect_uri
        return super().validate_redirect_uri(redirect_uri)


class SoloOAuthProvider(OAuthProvider):
    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        url = super()._get_resource_url(path)
        if url is not None and path is not None and not path.strip("/"):
            return AnyHttpUrl(str(url).rstrip("/"))
        return url

    def __init__(self) -> None:
        super().__init__(
            base_url=f"{Config.USER.MCP_PUBLIC_BASE_URL.rstrip('/')}{WALLET_RESOURCE_PATH}",
            issuer_url=f"{Config.USER.MCP_PUBLIC_BASE_URL.rstrip('/')}/",
            required_scopes=[WALLET_SCOPE],
            revocation_options=RevocationOptions(enabled=True),
        )
        self.authlibStore = OAuthStore()
        self.authlibServer = MansaAuthorizationServer(self.authlibStore)
        self.pending: dict[str, dict] = {}

    def clear(self) -> None:
        self.pending.clear()
        revokedJtiTimes.clear()
        self.authlibStore.clear()

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

    def get_routes(self, mcp_path: str | None = None) -> list[Route]:
        routes = super().get_routes(mcp_path)
        rebuilt: list[Route] = []
        for route in routes:
            path = getattr(route, "path", "")
            methods = set(getattr(route, "methods", ()) or ())
            if path == "/token" and "POST" in methods:
                rebuilt.append(
                    Route(
                        "/token",
                        endpoint=cors_middleware(self._tokenEndpoint, ["POST", "OPTIONS"]),
                        methods=["POST", "OPTIONS"],
                    )
                )
            elif path == "/revoke" and "POST" in methods:
                rebuilt.append(
                    Route(
                        "/revoke",
                        endpoint=cors_middleware(self._revokeEndpoint, ["POST", "OPTIONS"]),
                        methods=["POST", "OPTIONS"],
                    )
                )
            else:
                rebuilt.append(route)
        return rebuilt

    @staticmethod
    async def _oauthRequest(request: Request) -> FastAPIStyleRequest:
        params: dict[str, Any] = dict(request.query_params)
        form = FormData()
        try:
            form = await request.form()
        except Exception:
            pass
        for key, value in form.multi_items():
            params[key] = value
        return FastAPIStyleRequest(request.method, str(request.url), params, request.headers)

    async def _tokenEndpoint(self, request: Request) -> Response:
        return self.authlibServer.create_token_response(await self._oauthRequest(request))

    async def _revokeEndpoint(self, request: Request) -> Response:
        return self.authlibServer.create_endpoint_response("revocation", await self._oauthRequest(request))

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
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

    def take_pending(self, requestId: str) -> dict | None:
        item = self.pending.pop(requestId, None)
        if not item or item["expires_at"] < time.time():
            return None
        return item

    def peek_pending(self, requestId: str) -> dict | None:
        item = self.pending.get(requestId)
        if not item or item["expires_at"] < time.time():
            self.pending.pop(requestId, None)
            return None
        return item

    def issue_code(
        self,
        clientId: str,
        userId: str,
        sessionId: str,
        codeChallenge: str,
        redirectUri: str,
        redirectProvided: bool,
        scopes: list[str],
        resource: str | None,
    ) -> str:
        code = secrets.token_urlsafe(32)
        scope = " ".join(scopes or [WALLET_SCOPE])
        self.authlibStore.codes[code] = CodeRecord(
            code=code,
            clientId=clientId,
            redirectUri=redirectUri,
            scope=scope,
            code_challenge=codeChallenge,
            code_challenge_method="S256",
            sessionId=str(sessionId),
            userId=str(userId),
            resource=resource,
            redirect_uri_provided_explicitly=redirectProvided,
        )
        return code

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        record = self.authlibStore.codes.get(authorization_code)
        if (
            not record
            or record.clientId != client.client_id
            or record.expiresAt < time.time()
            or not record.redirectUri
        ):
            return None
        return AuthorizationCode(
            code=record.code,
            scopes=record.scope.split(),
            expires_at=record.expiresAt,
            client_id=record.clientId,
            code_challenge=record.code_challenge or "",
            redirect_uri=AnyUrl(record.redirectUri),
            redirect_uri_provided_explicitly=record.redirect_uri_provided_explicitly,
            resource=record.resource,
            subject=record.userId,
        )

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        record = self.authlibStore.codes.pop(authorization_code.code, None)
        if not record or record.clientId != client.client_id:
            raise TokenError("invalid_grant", "authorization code does not exist")
        if record.expiresAt < time.time():
            raise TokenError("invalid_grant", "authorization code has expired")
        return self.mint(
            client.client_id,
            str(record.userId or ""),
            str(record.sessionId or ""),
            record.scope.split(),
            record.resource,
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        record = self.authlibStore.refreshTokens.get(refresh_token)
        if (
            not record
            or record.clientId != client.client_id
            or record.revoked
            or (record.expiresAt is not None and record.expiresAt < time.time())
        ):
            return None
        return RefreshToken(
            token=record.token,
            client_id=record.clientId,
            scopes=record.scope.split(),
            expires_at=int(record.expiresAt) if record.expiresAt is not None else None,
            resource=record.resource,
            subject=record.userId,
        )

    async def exchange_refresh_token(
        self,
        client: OAuthClientInformationFull,
        refresh_token: RefreshToken,
        scopes: list[str],
    ) -> OAuthToken:
        record = self.authlibStore.refreshTokens.get(refresh_token.token)
        if not record or record.clientId != client.client_id:
            raise TokenError("invalid_grant", "refresh token does not exist")
        if record.expiresAt is not None and record.expiresAt < time.time():
            raise TokenError("invalid_grant", "refresh token has expired")
        record.revoked = True
        return self.mint(
            client.client_id,
            str(record.userId or ""),
            str(record.sessionId or ""),
            scopes or record.scope.split(),
            record.resource,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        db = SessionLocal()
        try:
            return verifyMcpAccessToken(token, db)
        finally:
            db.close()

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        value = getattr(token, "token", "")
        if not value:
            return
        record = self.authlibStore.refreshTokens.get(value)
        if record is not None:
            record.revoked = True
            self.authlibStore.refreshTokens.pop(value, None)
            return
        try:
            payload = decodeToken(value)
        except Exception:
            return
        jti = str(payload.get("jti") or "")
        if jti:
            now = time.time()
            cutoff = now - ACCESS_TTL_SECONDS
            for oldJti, seenAt in list(revokedJtiTimes.items()):
                if seenAt < cutoff:
                    del revokedJtiTimes[oldJti]
                    REVOKED_ACCESS_JTIS.discard(oldJti)
            revokedJtiTimes[jti] = now
            REVOKED_ACCESS_JTIS.add(jti)

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

    def mint(self, clientId: str, userId: str, sessionId: str, scopes: list[str], resource: str | None) -> OAuthToken:
        useScopes = scopes or [WALLET_SCOPE]
        client = StaticClient(
            clientId,
            Config.USER.MCP_OAUTH_CLIENT_SECRET,
            [resource or resourceUrl()],
        )
        user = OAuthUser(userId=str(userId), sessionId=str(sessionId))
        issued = self.authlibServer.generate_token(
            "authorization_code",
            client,
            user=user,
            scope=" ".join(useScopes),
            expires_in=ACCESS_TTL_SECONDS,
        )
        refreshValue = str(issued["refresh_token"])
        record = self.authlibStore.refreshTokens.get(refreshValue) or RefreshRecord(
            token=refreshValue,
            clientId=clientId,
            scope=" ".join(useScopes),
            sessionId=str(sessionId),
            userId=str(userId),
            expiresAt=time.time() + REFRESH_TTL_SECONDS,
        )
        record.resource = resource or resourceUrl()
        self.authlibStore.refreshTokens[refreshValue] = record
        return OAuthToken(
            access_token=str(issued["access_token"]),
            token_type="Bearer",
            expires_in=int(issued.get("expires_in", ACCESS_TTL_SECONDS)),
            scope=str(issued.get("scope", " ".join(useScopes))),
            refresh_token=refreshValue,
        )


class SoloAuth(MultiAuth):
    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        if self.server is not None:
            getUrl = getattr(self.server, "_get_resource_url", None)
            if callable(getUrl):
                return getUrl(path)
        return super()._get_resource_url(path)

    def get_middleware(self) -> list:
        return loopbackMiddleware(self)
