"""Native OAuth provider for the wallet MCP (MCP SDK Protocol, no external IdP).

Implements mcp.server.auth.provider.OAuthAuthorizationServerProvider against
existing primitives only: SessionManager rows (revocation source of truth),
createAccessToken/verifyAccessToken (HS256, aud=resource URL/scope=wallet),
authenticateUser-or-session-cookie at the consent step, getCurrentUser identity
at the resource server.

Storage is ephemeral in-memory (clients/codes/refresh/pending/denylist).
UserSession reuse genuinely fails for these bindings: UserSession has no fields
for redirect_uris/secrets (DCR), code_challenge/expiry/single-use (codes), or
client bindings (500-char userAgent unfit, mixing concerns). New tables
unnecessary: codes live 10min, DCR clients re-register on restart, refresh and
access are stateless JWTs bound to sessionId with revocation enforced at the RS
via SessionManager + denylist. Single-instance ceiling noted below.

# ponytail: in-memory AS state, per-process only; move clients/codes/denylist
# to DB tables (parent c3d4) if multi-instance or restart-persistent DCR matters.
"""

from __future__ import annotations

import secrets
import time

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    OAuthAuthorizationServerProvider,
    RefreshToken,
    TokenError,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyUrl

from main.app.authentication.oauth_shared import (
    ISSUER_URL,
    RESOURCE_METADATA_URL,
    RESOURCE_URL,
    WALLET_SCOPE,
    revokedAccessJtis,
)
from main.app.authentication.util import createAccessToken, verifyAccessToken

CODE_TTL_SECONDS = 600
ACCESS_TTL_SECONDS = 3600
REFRESH_TTL_SECONDS = 30 * 24 * 3600


class WalletOAuthProvider(OAuthAuthorizationServerProvider[AuthorizationCode, RefreshToken, AccessToken]):
    """In-memory AS for native users. One instance shared per process."""

    def __init__(self) -> None:
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.codes: dict[str, AuthorizationCode] = {}
        self.codeSessions: dict[str, str] = {}
        self.refreshTokens: dict[str, RefreshToken] = {}
        self.refreshSessions: dict[str, str] = {}
        self.pending: dict[str, dict] = {}
        # Alias to the shared leaf set: single revocation source of truth.
        self.revokedAccess: set[str] = revokedAccessJtis

    def clear(self) -> None:
        self.clients.clear()
        self.codes.clear()
        self.codeSessions.clear()
        self.refreshTokens.clear()
        self.refreshSessions.clear()
        self.pending.clear()
        self.revokedAccess.clear()

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        if not client_info.client_id:
            raise ValueError("client_id required")
        self.clients[client_info.client_id] = client_info

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        if params.scopes:
            for scope in params.scopes:
                if scope != WALLET_SCOPE:
                    raise AuthorizeError("invalid_scope", f"unsupported scope {scope}")
        requestId = secrets.token_urlsafe(16)
        self.pending[requestId] = {
            "client_id": client.client_id,
            "scopes": params.scopes or [WALLET_SCOPE],
            "code_challenge": params.code_challenge,
            "redirect_uri": str(params.redirect_uri),
            "redirect_provided": params.redirect_uri_provided_explicitly,
            "resource": params.resource or RESOURCE_URL,
            "state": params.state,
            "expires_at": time.time() + CODE_TTL_SECONDS,
        }
        return f"{ISSUER_URL}/auth/consent?request_id={requestId}"

    def take_pending(self, request_id: str) -> dict | None:
        item = self.pending.pop(request_id, None)
        if not item:
            return None
        if item["expires_at"] < time.time():
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
        resource: str,
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
        if not code:
            return None
        if code.client_id != client.client_id:
            return None
        return code

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        stored = self.codes.pop(authorization_code.code, None)
        sessionId = self.codeSessions.pop(authorization_code.code, "")
        if not stored:
            raise TokenError("invalid_grant", "authorization code does not exist")
        userId = str(stored.subject or "")
        scopes = stored.scopes or [WALLET_SCOPE]
        resource = stored.resource or RESOURCE_URL
        accessJti = secrets.token_urlsafe(16)
        access = createAccessToken(
            {
                "userId": userId,
                "sessionId": str(sessionId),
                "client_id": client.client_id,
                "aud": resource,
                "scope": " ".join(scopes),
                "jti": accessJti,
            },
        )
        refreshValue = secrets.token_urlsafe(32)
        self.refreshTokens[refreshValue] = RefreshToken(
            token=refreshValue,
            client_id=str(client.client_id),
            scopes=scopes,
            expires_at=int(time.time()) + REFRESH_TTL_SECONDS,
            resource=resource,
            subject=userId,
        )
        self.refreshSessions[refreshValue] = str(sessionId)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL_SECONDS,
            scope=" ".join(scopes),
            refresh_token=refreshValue,
        )

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        stored = self.refreshTokens.get(refresh_token)
        if not stored:
            return None
        if stored.client_id != client.client_id:
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
        userId = str(stored.subject or "")
        resource = stored.resource or RESOURCE_URL
        useScopes = scopes or stored.scopes
        accessJti = secrets.token_urlsafe(16)
        access = createAccessToken(
            {
                "userId": userId,
                "sessionId": str(sessionId),
                "client_id": client.client_id,
                "aud": resource,
                "scope": " ".join(useScopes),
                "jti": accessJti,
            },
        )
        nextRefresh = secrets.token_urlsafe(32)
        self.refreshTokens[nextRefresh] = RefreshToken(
            token=nextRefresh,
            client_id=str(client.client_id),
            scopes=useScopes,
            expires_at=int(time.time()) + REFRESH_TTL_SECONDS,
            resource=resource,
            subject=userId,
        )
        self.refreshSessions[nextRefresh] = str(sessionId)
        return OAuthToken(
            access_token=access,
            token_type="Bearer",
            expires_in=ACCESS_TTL_SECONDS,
            scope=" ".join(useScopes),
            refresh_token=nextRefresh,
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        try:
            payload = verifyAccessToken(token)
        except Exception:
            return None
        jti = str(payload.get("jti") or "")
        if jti and jti in self.revokedAccess:
            return None
        userId = str(payload.get("userId") or "")
        if not userId:
            return None
        scopeRaw = payload.get("scope") or ""
        scopes = scopeRaw.split() if isinstance(scopeRaw, str) and scopeRaw else [WALLET_SCOPE]
        resource = payload.get("aud")
        exp = payload.get("exp")
        expiresAt = None
        if isinstance(exp, (int, float)):
            expiresAt = int(exp)
        return AccessToken(
            token=token,
            client_id=str(payload.get("client_id") or ""),
            scopes=scopes,
            expires_at=expiresAt,
            resource=str(resource) if resource else None,
            subject=userId,
            claims={"iss": ISSUER_URL},
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
            jti = str(payload.get("jti") or "")
            if jti:
                self.revokedAccess.add(jti)
        except Exception:
            return


walletOAuthProvider = WalletOAuthProvider()


def is_access_revoked(token: str) -> bool:
    try:
        payload = verifyAccessToken(token)
    except Exception:
        return False
    jti = str(payload.get("jti") or "")
    return bool(jti) and jti in walletOAuthProvider.revokedAccess
