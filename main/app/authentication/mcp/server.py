from __future__ import annotations

import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from authlib.common.security import generate_token
from authlib.oauth2.rfc6749 import AuthorizationServer, OAuth2Request
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant, RefreshTokenGrant
from authlib.oauth2.rfc7009 import RevocationEndpoint
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9068 import JWTBearerTokenGenerator
from joserfc.jwk import OctKey
from starlette.responses import JSONResponse, RedirectResponse, Response

from config import Config, LOCALHOST_ADDRESSES
from main.app.authentication.constants import (
    ACCESS_TTL,
    CODE_TTL,
    ISSUER,
    REFRESH_TTL,
    WALLET_SCOPE,
)
from main.app.authentication.verifier import REVOKED_ACCESS_JTIS, oauthTokenValidator, resourceUrl


@dataclass
class OAuthUser:
    userId: str
    sessionId: str | None = None
    username: str | None = None
    roles: list[str] = field(default_factory=list)
    email: str | None = None

    def get_user_id(self) -> str:
        return self.userId


@dataclass
class CodeRecord:
    code: str
    clientId: str
    redirectUri: str | None
    scope: str
    state: str | None = None
    code_challenge: str | None = None
    code_challenge_method: str | None = None
    sessionId: str | None = None
    userId: str | None = None
    resource: str | None = None
    redirect_uri_provided_explicitly: bool = False
    expiresAt: float = field(default_factory=lambda: time.time() + CODE_TTL)

    def get_redirect_uri(self) -> str | None:
        return self.redirectUri

    def get_scope(self) -> str:
        return self.scope


@dataclass
class RefreshRecord:
    token: str
    clientId: str
    scope: str
    sessionId: str | None
    userId: str
    resource: str | None = None
    expiresAt: float = field(default_factory=lambda: time.time() + REFRESH_TTL)
    revoked: bool = False

    def check_client(self, client: "StaticClient") -> bool:
        return not self.revoked and self.expiresAt > time.time() and client.get_client_id() == self.clientId

    def get_scope(self) -> str:
        return self.scope

    def get_user_id(self) -> str:
        return self.userId


class StaticClient:
    def __init__(
        self,
        clientId: str,
        clientSecret: str,
        redirectUris: list[str] | None = None,
        resource: str | None = None,
    ):
        self.clientId = clientId
        self.clientSecret = clientSecret
        self.redirectUris = redirectUris or []
        self.resource = resource

    def get_client_id(self) -> str:
        return self.clientId

    def get_default_redirect_uri(self) -> str | None:
        return self.redirectUris[0] if self.redirectUris else None

    def get_allowed_scope(self, scope: str | None) -> str:
        return scope or WALLET_SCOPE

    def check_redirect_uri(self, redirectUri: str | None) -> bool:
        if not redirectUri:
            return False
        if redirectUri in self.redirectUris:
            return True
        try:
            parsed = urlparse(redirectUri)
            host = (parsed.hostname or "").strip("[]").lower()
        except Exception:
            return False
        return parsed.scheme in ("http", "http+unix", "custom") and (
            host in LOCALHOST_ADDRESSES or parsed.scheme == "custom"
        )

    def check_client_secret(self, secret: str) -> bool:
        return secrets.compare_digest(secret or "", self.clientSecret)

    def check_endpoint_auth_method(self, method: str, endpoint: str) -> bool:
        return method in ("client_secret_basic", "client_secret_post", "none")

    def check_response_type(self, responseType: str) -> bool:
        return responseType == "code"

    def check_grant_type(self, grantType: str) -> bool:
        return grantType in ("authorization_code", "refresh_token")


class OAuthStore:
    def __init__(self) -> None:
        self.codes: dict[str, CodeRecord] = {}
        self.refreshTokens: dict[str, RefreshRecord] = {}

    def clear(self) -> None:
        self.codes.clear()
        self.refreshTokens.clear()
        REVOKED_ACCESS_JTIS.clear()


class FastAPIStyleRequest(OAuth2Request):
    def __init__(self, method: str, uri: str, params: dict[str, Any], headers: Any = None):
        os.environ.setdefault("AUTHLIB_INSECURE_TRANSPORT", "1")
        super().__init__(method, uri, headers=headers or {})
        self.payload = BasicOAuth2Payload(dict(params))
        self._params = dict(params)

    @property
    def args(self) -> dict[str, Any]:
        return self._params

    @property
    def form(self) -> dict[str, Any]:
        return self._params


class MansaTokenGenerator(JWTBearerTokenGenerator):
    def __init__(self) -> None:
        super().__init__(
            issuer=ISSUER,
            alg="HS256",
            refresh_token_generator=lambda **kwargs: generate_token(48),
            expires_generator=lambda client, grant_type: ACCESS_TTL,
        )

    def get_jwks(self) -> OctKey:
        return OctKey.import_key(Config.USER.JWT_SECRET_KEY)

    def get_audiences(self, client: StaticClient, user: OAuthUser | None, scope: str) -> str:
        return client.resource or resourceUrl()

    def get_extra_claims(
        self, client: StaticClient, grantType: str, user: OAuthUser | None, scope: str
    ) -> dict[str, Any]:
        if not user:
            return {}
        claims: dict[str, Any] = {"userId": str(user.get_user_id())}
        if user.sessionId:
            claims["sessionId"] = user.sessionId
        if user.roles:
            claims["roles"] = user.roles
        if user.email:
            claims["email"] = user.email
        return claims


class MansaAuthorizationCodeGrant(AuthorizationCodeGrant):
    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post"]

    def save_authorization_code(self, code: str, request: FastAPIStyleRequest) -> None:
        store: OAuthStore = self.server.store
        user = request.user
        record = CodeRecord(
            code=code,
            clientId=request.client.get_client_id(),
            redirectUri=request.payload.redirect_uri,
            scope=request.scope or "",
            state=request.payload.state,
            code_challenge=request.payload.data.get("code_challenge"),
            code_challenge_method=request.payload.data.get("code_challenge_method"),
            sessionId=getattr(user, "sessionId", None),
            userId=user.get_user_id() if user else None,
        )
        store.codes[code] = record

    def query_authorization_code(self, code: str, client: StaticClient) -> CodeRecord | None:
        store: OAuthStore = self.server.store
        record = store.codes.get(code)
        if record and record.clientId == client.get_client_id() and record.expiresAt > time.time():
            return record
        return None

    def delete_authorization_code(self, authorizationCode: CodeRecord) -> None:
        store: OAuthStore = self.server.store
        store.codes.pop(authorizationCode.code, None)

    def authenticate_user(self, authorizationCode: CodeRecord) -> OAuthUser:
        return OAuthUser(
            userId=authorizationCode.userId or "",
            sessionId=authorizationCode.sessionId,
        )


class MansaRefreshTokenGrant(RefreshTokenGrant):
    INCLUDE_NEW_REFRESH_TOKEN = True
    TOKEN_ENDPOINT_AUTH_METHODS = ["client_secret_basic", "client_secret_post"]

    def authenticate_refresh_token(self, refreshToken: str) -> RefreshRecord | None:
        store: OAuthStore = self.server.store
        record = store.refreshTokens.get(refreshToken)
        if record and record.expiresAt > time.time() and not record.revoked:
            return record
        return None

    def authenticate_user(self, refreshToken: RefreshRecord) -> OAuthUser:
        return OAuthUser(userId=refreshToken.userId, sessionId=refreshToken.sessionId)

    def revoke_old_credential(self, refreshToken: RefreshRecord) -> None:
        refreshToken.revoked = True


@dataclass
class AccessRevocationRecord:
    jti: str
    clientId: str

    def check_client(self, client: "StaticClient") -> bool:
        return client.get_client_id() == self.clientId


class MansaRevocationEndpoint(RevocationEndpoint):
    CLIENT_AUTH_METHODS = ["client_secret_basic", "client_secret_post"]

    def query_token(self, tokenString: str, tokenTypeHint: str | None) -> RefreshRecord | AccessRevocationRecord | None:
        store: OAuthStore = self.server.store
        record = store.refreshTokens.get(tokenString)
        if record:
            return record
        if tokenString.count(".") != 2:
            return None
        try:
            claims = oauthTokenValidator.authenticate_token(tokenString)
        except Exception:
            return None
        return AccessRevocationRecord(jti=claims.get("jti", ""), clientId=claims.get("client_id", ""))

    def revoke_token(self, token: RefreshRecord | AccessRevocationRecord, request: FastAPIStyleRequest) -> None:
        if isinstance(token, AccessRevocationRecord):
            if token.jti:
                REVOKED_ACCESS_JTIS.add(token.jti)
            return
        token.revoked = True
        if token.token in self.server.store.refreshTokens:
            self.server.store.refreshTokens.pop(token.token, None)


class MansaAuthorizationServer(AuthorizationServer):
    def __init__(self, store: OAuthStore) -> None:
        super().__init__(scopes_supported=[WALLET_SCOPE])
        self.store = store
        self.register_grant(MansaAuthorizationCodeGrant, [CodeChallenge(required=True)])
        self.register_grant(MansaRefreshTokenGrant)
        self.register_endpoint(MansaRevocationEndpoint)
        self.register_token_generator("default", MansaTokenGenerator())

    def query_client(self, client_id: str) -> StaticClient | None:
        clientId = Config.USER.MCP_OAUTH_CLIENT_ID
        secret = Config.USER.MCP_OAUTH_CLIENT_SECRET
        if not clientId or not secret or client_id != clientId:
            return None
        return StaticClient(clientId, secret, [resourceUrl()])

    def save_token(self, token: dict[str, Any], request: FastAPIStyleRequest) -> None:
        user = request.user
        if not user or not token.get("refresh_token"):
            return
        refresh = token["refresh_token"]
        record = RefreshRecord(
            token=refresh,
            clientId=request.client.get_client_id(),
            scope=token.get("scope", ""),
            sessionId=getattr(user, "sessionId", None),
            userId=str(user.get_user_id()),
        )
        self.store.refreshTokens[refresh] = record

    def create_oauth2_request(self, request: Any) -> FastAPIStyleRequest:
        if isinstance(request, FastAPIStyleRequest):
            return request
        return FastAPIStyleRequest("GET", Config.USER.MCP_PUBLIC_BASE_URL, dict(request))

    def create_json_request(self, request: Any) -> Any:
        return request

    def handle_response(self, status: int, body: Any, headers: Any) -> Response:
        headers = dict(headers or {})
        if isinstance(body, (dict, list)):
            return JSONResponse(body, status_code=status, headers=headers)
        if status in (302, 303, 307, 308) and headers.get("Location"):
            return RedirectResponse(headers["Location"], status_code=status)
        return Response(str(body or ""), status_code=status, headers=headers)

    def send_signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        return None
