from __future__ import annotations

import secrets
import time
from typing import Any
from urllib.parse import urlparse

from fastmcp.server.auth import AccessToken, MultiAuth, OAuthProvider
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError, RefreshToken
from mcp.server.auth.routes import cors_middleware
from mcp.server.auth.settings import RevocationOptions
from mcp.shared.auth import OAuthClientInformationFull
from pydantic import AnyHttpUrl, AnyUrl
from starlette.datastructures import FormData
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route

from config import Config, LOCALHOST_ADDRESSES, SessionLocal
from main.app.authentication.constants import CODE_TTL, WALLET_RESOURCE_PATH, WALLET_SCOPE
from main.app.authentication.mcp.server import (
    CodeRecord,
    FastAPIStyleRequest,
    MansaAuthorizationServer,
    OAuthStore,
)
from main.app.authentication.mcp.verifier import verifyMcpAccessToken
from main.app.authentication.session import SessionManager
from main.app.authentication.tokens import decodeToken
from main.app.authentication.util import loopbackMiddleware
from main.app.authentication.verifier import REVOKED_ACCESS_JTIS


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
        self.authlibStore.clear()

    def buildClient(self) -> OAuthClientInformationFull | None:
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
        client = self.buildClient()
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
                        endpoint=cors_middleware(self.tokenEndpoint, ["POST", "OPTIONS"]),
                        methods=["POST", "OPTIONS"],
                    )
                )
            elif path == "/revoke" and "POST" in methods:
                rebuilt.append(
                    Route(
                        "/revoke",
                        endpoint=cors_middleware(self.revokeEndpoint, ["POST", "OPTIONS"]),
                        methods=["POST", "OPTIONS"],
                    )
                )
            else:
                rebuilt.append(route)
        return rebuilt

    @staticmethod
    async def oauthRequest(request: Request) -> FastAPIStyleRequest:
        params: dict[str, Any] = dict(request.query_params)
        form = FormData()
        try:
            form = await request.form()
        except Exception:
            pass
        for key, value in form.multi_items():
            params[key] = value
        return FastAPIStyleRequest(request.method, str(request.url), params, request.headers)

    async def tokenEndpoint(self, request: Request) -> Response:
        return self.authlibServer.create_token_response(await self.oauthRequest(request))

    async def revokeEndpoint(self, request: Request) -> Response:
        oauthRequest = await self.oauthRequest(request)
        response = self.authlibServer.create_endpoint_response("revocation", oauthRequest)
        if response.status_code == 200:
            tokenValue = str(oauthRequest.form.get("token") or "")
            if tokenValue:
                await self.revoke_token(AccessToken(token=tokenValue, client_id="", scopes=[]))
        return response

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
            "expires_at": time.time() + CODE_TTL,
        }
        return f"{str(self.base_url).rstrip('/')}/oauth/login?request_id={requestId}"

    def takePending(self, requestId: str) -> dict | None:
        item = self.pending.pop(requestId, None)
        if not item or item["expires_at"] < time.time():
            return None
        return item

    def peekPending(self, requestId: str) -> dict | None:
        item = self.pending.get(requestId)
        if not item or item["expires_at"] < time.time():
            self.pending.pop(requestId, None)
            return None
        return item

    def issueCode(
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
        userId: Any = None
        sessionId: Any = None
        record = self.authlibStore.refreshTokens.get(value)
        if record is not None:
            record.revoked = True
            self.authlibStore.refreshTokens.pop(value, None)
            userId, sessionId = record.userId, record.sessionId
        else:
            try:
                payload = decodeToken(value)
            except Exception:
                return
            jti = str(payload.get("jti") or "")
            if jti:
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


class SoloAuth(MultiAuth):
    def _get_resource_url(self, path: str | None = None) -> AnyHttpUrl | None:
        if self.server is not None:
            getUrl = getattr(self.server, "_get_resource_url", None)
            if callable(getUrl):
                return getUrl(path)
        return super()._get_resource_url(path)

    def get_middleware(self) -> list:
        return loopbackMiddleware(self)
