"""Wallet MCP OAuth dance: SDK-native AS (DCR + PKCE + refresh) over user sessions.

End-to-end through the production wire (wallet router + consent router + SDK
auth routes + AuthConfig-guarded /wallet/mcp): DCR registers a client,
/authorize redirects to the consent UI, approving mints a PKCE-bound code,
/token exchanges it for our-shape HS256 (aud=resource, scope=wallet), and the
dance token reads the approver's OWN wallet over MCP. Legacy session JWTs
(without aud/scope) keep working; the shared-pool service loopback passes the
outer transport check but never resolves to a user wallet.
"""

import base64
import hashlib
import json
import os
import secrets
import sys
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi_mcp import AuthConfig, FastApiMCP

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastmcp import Client
from fastmcp.client.client import StreamableHttpTransport

from config import getSession
from main.app.authentication.mcp_oauth_provider import (
    ISSUER_URL,
    RESOURCE_METADATA_URL,
    RESOURCE_URL,
    walletOAuthProvider,
)
from main.app.authentication.util import verifyMcpTransport
from main.controller.authentication_controller import router as authenticationRouter
from main.controller.wallet_controller import router as walletRouter
from main.service.authentication_service import AuthenticationService
from main.service.wallet_service import WALLET_MCP_OPERATIONS
from tests.test_wallet_mcp import _live_ok

CALLBACK_URL = "http://127.0.0.1:8080/oauth/callback"


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


@pytest.fixture(autouse=True)
def clear_oauth_state():
    walletOAuthProvider.clear()
    yield
    walletOAuthProvider.clear()


def _build_dance_app(dbSession):
    """Production wire: auth + wallet routers, SDK AS routes, guarded mount."""
    from main.utils.errors import registerErrorHandlers

    from main.app.authentication.introspect import introspectToken
    from main.app.authentication.service_token import verifyServiceToken
    from main.app.wallet import auth as walletAuth

    class _FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def _fakePost(url, json=None, headers=None, timeout=None):
        try:
            ok = verifyServiceToken(dbSession, (headers or {}).get("X-Service-Token", ""))
        except TypeError:
            ok = verifyServiceToken((headers or {}).get("X-Service-Token", ""))
        if not ok:
            return _FakeResp(401, {"error": "Unauthorized"})
        try:
            payload = introspectToken(dbSession, (json or {}).get("token"))
        except Exception:
            return _FakeResp(401, {"error": "Unauthorized"})
        return _FakeResp(200, payload)

    walletAuth.httpx.post = _fakePost  # type: ignore[method-assign]

    app = FastAPI()
    registerErrorHandlers(app)
    app.include_router(authenticationRouter)
    app.include_router(walletRouter)

    mcp = FastApiMCP(
        app,
        name="Mansa Wallet MCP",
        include_operations=WALLET_MCP_OPERATIONS,
        headers=["authorization"],
        auth_config=AuthConfig(dependencies=[Depends(verifyMcpTransport)]),
    )
    mcp.mount_http(app, mount_path="/wallet/mcp")
    app.routes.extend(AuthenticationService.oauthRoutes())

    app.dependency_overrides[getSession] = lambda: dbSession
    return app


def _mcp_client(app, headers=None):
    def asgiFactory(**kwargs):
        clientArgs = {
            key: value for key, value in kwargs.items() if key in ("headers", "auth", "follow_redirects", "timeout")
        }
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://apiserver", **clientArgs)

    transport = StreamableHttpTransport(
        url="http://apiserver/wallet/mcp",
        httpx_client_factory=asgiFactory,
        headers=headers or {},
    )
    return Client(transport=transport)


def _mintServiceToken(dbSession):
    """Independent loopback token (same shape the pool sends at transport)."""
    from main.app.authentication.service_token import createServiceToken

    return createServiceToken(dbSession)


def _makeDanceUser(dbSession, username, password="dancepass"):
    from main.app.authentication.util import hashPassword
    from main.models.user import User

    user = User(username=username, email=f"{username}@example.com", passwordHash=hashPassword(password), roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    return user


def _seedDanceWallet(dbSession, user, ticker="PETR4", quantity=10, price=10.0):
    from main.app.wallet.entries import EntryCreate, EntriesManager
    from main.app.wallet.wallets import WalletsManager

    wallet = WalletsManager.getMyWallet(dbSession, user.userId)
    EntriesManager.addEntry(
        dbSession,
        wallet,
        EntryCreate(
            side="Compra",
            asset_type="ACOES",
            ticker=ticker,
            date=date(2026, 1, 2),
            quantity=quantity,
            price=price,
        ),
    )
    return wallet


def _danceTokens(http, username, password="dancepass"):
    """DCR -> authorize -> consent -> code -> token. Returns (access, refresh, clientId)."""
    verifier = secrets.token_urlsafe(32)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")

    reg = http.post(
        "/register",
        json={
            "redirect_uris": [CALLBACK_URL],
            "token_endpoint_auth_method": "none",
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "scope": "wallet",
            "client_name": "pytest-dance",
        },
    )
    assert reg.status_code == 201, reg.text
    clientId = reg.json()["client_id"]

    auth = http.get(
        "/authorize",
        params={
            "client_id": clientId,
            "redirect_uri": CALLBACK_URL,
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "wallet",
            "resource": RESOURCE_URL,
            "state": "dance-state",
        },
        follow_redirects=False,
    )
    assert auth.status_code == 302, auth.text
    consentUrl = auth.headers["location"]
    assert "/auth/consent?request_id=" in consentUrl

    form = http.get(consentUrl)
    assert form.status_code == 200

    requestId = parse_qs(urlparse(consentUrl).query)["request_id"][0]
    approval = http.post(
        "/auth/consent",
        data={"request_id": requestId, "username": username, "password": password, "approve": "wallet"},
        follow_redirects=False,
    )
    assert approval.status_code == 302, approval.text
    callbackQuery = parse_qs(urlparse(approval.headers["location"]).query)
    assert callbackQuery["state"][0] == "dance-state"
    code = callbackQuery["code"][0]

    token = http.post(
        "/token",
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": CALLBACK_URL,
            "client_id": clientId,
            "code_verifier": verifier,
        },
    )
    assert token.status_code == 200, token.text
    body = token.json()
    assert body["token_type"] == "Bearer"
    assert body["scope"] == "wallet"
    return body["access_token"], body.get("refresh_token"), clientId


class TestDanceMetadata:
    def test_authorization_server_metadata_resolves(self, dbSession):
        from fastapi.testclient import TestClient

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            resp = http.get("/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        body = resp.json()
        assert body["issuer"].rstrip("/") == ISSUER_URL.rstrip("/")
        assert body["authorization_endpoint"].endswith("/authorize")
        assert body["token_endpoint"].endswith("/token")
        assert body["registration_endpoint"].endswith("/register")
        assert body["code_challenge_methods_supported"] == ["S256"]

    def test_protected_resource_metadata_resolves(self, dbSession):
        from fastapi.testclient import TestClient

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            resp = http.get("/.well-known/oauth-protected-resource/wallet/mcp")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resource"] == RESOURCE_URL
        assert body["scopes_supported"] == ["wallet"]
        assert any(server.rstrip("/") == ISSUER_URL.rstrip("/") for server in body["authorization_servers"])

    def test_mount_get_stays_406_with_guard(self, dbSession):
        from fastapi.testclient import TestClient

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            assert http.get("/wallet/mcp").status_code == 406

    def test_bare_mcp_post_challenges_with_resource_metadata(self, dbSession):
        from fastapi.testclient import TestClient

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            resp = http.post("/wallet/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert resp.status_code == 401
        challenge = resp.headers.get("www-authenticate", "")
        assert RESOURCE_METADATA_URL in challenge


class TestFullDance:
    async def test_dance_token_reads_own_wallet(self, dbSession, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
        user = _makeDanceUser(dbSession, "danceuser")
        _seedDanceWallet(dbSession, user)

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            access, _, _ = _danceTokens(http, "danceuser")

        bearer = f"Bearer {access}"
        async with _mcp_client(app, headers={"Authorization": bearer}) as client:
            result = await client.call_tool("wallet_positions", {"authorization": bearer}, raise_on_error=False)

        assert not result.is_error
        payload = json.loads(result.content[0].text)
        assert [item["ticker"] for item in payload["items"]] == ["PETR4"]
        assert payload["equity_total"] == 300.0

    async def test_dance_tokens_are_cross_user_isolated(self, dbSession, monkeypatch):
        from fastapi.testclient import TestClient

        monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
        userA = _makeDanceUser(dbSession, "danceA")
        _seedDanceWallet(dbSession, userA)
        _makeDanceUser(dbSession, "danceB")

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            accessA, _, _ = _danceTokens(http, "danceA")
            accessB, _, _ = _danceTokens(http, "danceB")

        async with _mcp_client(app, headers={"Authorization": f"Bearer {accessB}"}) as client:
            resultB = await client.call_tool(
                "wallet_positions", {"authorization": f"Bearer {accessB}"}, raise_on_error=False
            )
        payloadB = json.loads(resultB.content[0].text)
        assert payloadB == {"items": [], "equity_total": 0.0}
        assert "PETR4" not in resultB.content[0].text

        async with _mcp_client(app, headers={"Authorization": f"Bearer {accessA}"}) as client:
            resultA = await client.call_tool(
                "wallet_positions", {"authorization": f"Bearer {accessA}"}, raise_on_error=False
            )
        assert [item["ticker"] for item in json.loads(resultA.content[0].text)["items"]] == ["PETR4"]

    async def test_refresh_rotates_and_reuse_rejected(self, dbSession):
        from fastapi.testclient import TestClient

        _makeDanceUser(dbSession, "refreshuser")
        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            access, refresh, clientId = _danceTokens(http, "refreshuser")

            rotated = http.post(
                "/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": clientId,
                },
            )
            assert rotated.status_code == 200, rotated.text
            newAccess = rotated.json()["access_token"]
            assert newAccess != access

            bearer = f"Bearer {newAccess}"
            async with _mcp_client(app, headers={"Authorization": bearer}) as client:
                result = await client.call_tool("wallet_positions", {"authorization": bearer}, raise_on_error=False)
            assert not result.is_error

            reuse = http.post(
                "/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh,
                    "client_id": clientId,
                },
            )
            assert reuse.status_code == 400
            assert reuse.json()["error"] == "invalid_grant"

    async def test_revoked_session_rejects_dance_token(self, dbSession):
        from fastapi.testclient import TestClient

        from main.app.authentication.session import SessionManager
        from main.app.authentication.util import verifyAccessToken

        _makeDanceUser(dbSession, "revokeuser")
        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            access, _, _ = _danceTokens(http, "revokeuser")

        payload = verifyAccessToken(access)
        userId = int(payload["userId"])
        assert SessionManager.revokeSession(dbSession, payload["sessionId"], userId)

        bearer = f"Bearer {access}"
        async with _mcp_client(app, headers={"Authorization": bearer}) as client:
            result = await client.call_tool("wallet_positions", {"authorization": bearer}, raise_on_error=False)
        assert result.is_error
        assert "401" in result.content[0].text

    async def test_revoked_access_token_rejected(self, dbSession):
        from fastapi.testclient import TestClient

        _makeDanceUser(dbSession, "denieduser")
        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            access, _, clientId = _danceTokens(http, "denieduser")

            revoke = http.post(
                "/revoke",
                data={"token": access, "client_id": clientId, "client_secret": ""},
            )
            assert revoke.status_code == 200, revoke.text

        # Outer transport rejects the denylisted jti at connect (401), so the
        # client never reaches the tool call.
        bearer = f"Bearer {access}"
        with pytest.raises(httpx.HTTPStatusError) as excinfo:
            async with _mcp_client(app, headers={"Authorization": bearer}):
                pass
        assert excinfo.value.response.status_code == 401


class TestBackCompatAndPool:
    async def test_legacy_session_jwt_still_200(self, dbSession):
        from fastapi.testclient import TestClient

        from main.app.authentication.session import SessionManager
        from main.app.authentication.util import createAccessToken
        from main.models.user import User

        user = User(username="legacyuser", email="legacyuser@example.com", passwordHash="h", roles="USER")
        dbSession.add(user)
        dbSession.commit()
        dbSession.refresh(user)
        session = SessionManager.createSession(dbSession, user.userId, "pytest")
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})

        app = _build_dance_app(dbSession)
        bearer = f"Bearer {token}"
        async with _mcp_client(app, headers={"Authorization": bearer}) as client:
            result = await client.call_tool("wallet_positions", {"authorization": bearer}, raise_on_error=False)
        assert not result.is_error
        assert json.loads(result.content[0].text) == {"items": [], "equity_total": 0.0}

    def test_legacy_static_header_still_200(self, dbSession):
        from fastapi.testclient import TestClient

        from main.app.authentication.session import SessionManager
        from main.app.authentication.util import createAccessToken
        from main.models.user import User

        user = User(username="staticuser", email="staticuser@example.com", passwordHash="h", roles="USER")
        dbSession.add(user)
        dbSession.commit()
        dbSession.refresh(user)
        session = SessionManager.createSession(dbSession, user.userId, "pytest")
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})

        app = _build_dance_app(dbSession)
        with TestClient(app, raise_server_exceptions=False) as http:
            resp = http.get("/wallet/positions", headers={"X-Access-Token": token})
        assert resp.status_code == 200

    async def test_pool_loopback_with_user_arg_reads_own_wallet(self, dbSession, monkeypatch):
        """msg-44 regression: service transport header + injected user JWT arg."""
        monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
        user = _makeDanceUser(dbSession, "pooluser")
        _seedDanceWallet(dbSession, user)

        from main.app.authentication.session import SessionManager
        from main.app.authentication.util import createAccessToken

        session = SessionManager.createSession(dbSession, user.userId, "pytest")
        userJwt = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})

        app = _build_dance_app(dbSession)
        loopback = _mintServiceToken(dbSession)
        async with _mcp_client(app, headers={"X-Service-Token": loopback}) as client:
            result = await client.call_tool(
                "wallet_positions", {"authorization": f"Bearer {userJwt}"}, raise_on_error=False
            )

        assert not result.is_error
        payload = json.loads(result.content[0].text)
        assert [item["ticker"] for item in payload["items"]] == ["PETR4"]
        assert payload["equity_total"] == 300.0

    async def test_service_token_never_resolves_to_wallet(self, dbSession):
        app = _build_dance_app(dbSession)
        loopback = _mintServiceToken(dbSession)
        bearer = f"Bearer {loopback}"
        async with _mcp_client(app, headers={"X-Service-Token": loopback}) as client:
            result = await client.call_tool("wallet_positions", {"authorization": bearer}, raise_on_error=False)
        assert result.is_error
        assert "401" in result.content[0].text

    def test_pool_wallet_entry_sends_loopback_header(self, dbSession):
        from main.app.orunmila.mcp import MCP_SERVERS, prepareServer
        from main.app.authentication.service_token import verifyServiceToken

        wallet = next(server for server in MCP_SERVERS if server["name"] == "wallet")
        prepared = prepareServer(wallet, dbSession)
        assert verifyServiceToken(dbSession, prepared["headers"]["X-Service-Token"])

    def test_inner_identity_rejects_service_payload(self, dbSession):
        """getCurrentUser requires user JWT: typ=service carries no user/session."""
        from fastapi import HTTPException

        from main.app.user.user import UserManager

        request = MagicMock()
        request.headers = {}
        request.cookies = {}
        with pytest.raises(HTTPException) as excinfo:
            UserManager.getCurrentUser(request, payload={"typ": "service"}, db=dbSession)
        assert excinfo.value.status_code == 401
