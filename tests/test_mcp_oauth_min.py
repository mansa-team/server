"""SoloAS (single-client OAuth for wallet MCP) — Task 4 of the slim own-AS plan.

Provider-level cycle plus HTTP-level flow through the mounted walletMcp http app
(simulates OpenCode: authorize -> login -> code -> token -> Bearer MCP call ->
refresh -> revoke). PKCE-S256, client_secret and redirect checks are enforced
by the SDK handlers; these tests pin the closed-client behavior on top.
"""

import base64
import hashlib
import os
import sys
from datetime import date
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from pydantic import AnyUrl

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import Config
from main.app.authentication import mcp_oauth_solo as solo
from main.app.authentication.session import SessionManager
from main.app.authentication.util import createAccessToken, hashPassword
from main.app.wallet.entries import EntriesManager, EntryCreate
from main.app.wallet.wallets import WalletsManager
from main.models.user import User
from tests.test_wallet_positions import _live_ok

CLIENT_ID = "test-opencode"
CLIENT_SECRET = "test-secret-not-production"
REDIRECT_URI = "http://localhost:8080/callback"
VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
CHALLENGE = base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")


def _use_test_env(monkeypatch, dbSession):
    monkeypatch.setattr(Config.USER, "MCP_OAUTH_CLIENT_ID", CLIENT_ID)
    monkeypatch.setattr(Config.USER, "MCP_OAUTH_CLIENT_SECRET", CLIENT_SECRET)
    monkeypatch.setattr(solo, "SessionLocal", lambda: dbSession)
    monkeypatch.setattr("main.controller.wallet_controller.SessionLocal", lambda: dbSession)
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    provider = solo.SoloOAuthProvider()
    solo.soloProvider.clear()
    solo.revokedAccessJtis.clear()
    return provider


def _seed_user(dbSession, username="oauthuser", password="correct-horse-9"):
    user = User(username=username, email=f"{username}@example.com", passwordHash=hashPassword(password), roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    return int(user.userId), session.sessionId


def _params(**override):
    from mcp.server.auth.provider import AuthorizationParams

    base = {
        "state": "xyz",
        "scopes": ["wallet"],
        "code_challenge": CHALLENGE,
        "redirect_uri": AnyUrl(REDIRECT_URI),
        "redirect_uri_provided_explicitly": True,
        "resource": None,
    }
    base.update(override)
    return AuthorizationParams(**base)


async def _login_code(provider, userId, sessionId, state="xyz"):
    client = await provider.get_client(CLIENT_ID)
    loginUrl = await provider.authorize(client, _params(state=state))
    requestId = parse_qs(urlparse(loginUrl).query)["request_id"][0]
    pending = provider.take_pending(requestId)
    return provider.issue_code(
        pending["client_id"],
        str(userId),
        sessionId,
        pending["code_challenge"],
        pending["redirect_uri"],
        pending["redirect_provided"],
        pending["scopes"],
        pending["resource"] or solo.publicMcpUrl(),
    )


async def test_full_cycle_provider_level(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    userId, sessionId = _seed_user(dbSession)

    client = await provider.get_client(CLIENT_ID)
    assert client is not None
    loginUrl = await provider.authorize(client, _params())
    assert "/oauth/login?request_id=" in loginUrl

    code = await _login_code(provider, userId, sessionId)
    stored = await provider.load_authorization_code(client, code)
    assert stored is not None
    tokens = await provider.exchange_authorization_code(client, stored)
    assert tokens.scope == "wallet"
    assert tokens.refresh_token

    access = await provider.load_access_token(tokens.access_token)
    assert access is not None and access.subject == str(userId)

    rotated = await provider.exchange_refresh_token(
        client, await provider.load_refresh_token(client, tokens.refresh_token), []
    )
    assert rotated.refresh_token != tokens.refresh_token
    assert await provider.load_refresh_token(client, tokens.refresh_token) is None

    await provider.revoke_token(await provider.load_access_token(rotated.access_token))
    assert await provider.load_access_token(rotated.access_token) is None
    await provider.revoke_token(await provider.load_refresh_token(client, rotated.refresh_token))
    assert await provider.load_refresh_token(client, rotated.refresh_token) is None


async def test_closed_client_and_scopes(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    assert await provider.get_client("unknown") is None
    from mcp.server.auth.provider import AuthorizeError

    client = await provider.get_client(CLIENT_ID)
    with pytest.raises(AuthorizeError):
        await provider.authorize(client, _params(scopes=["admin"]))
    with pytest.raises(RuntimeError):
        await provider.register_client(client)


async def test_empty_secret_refuses_authorize(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    monkeypatch.setattr(Config.USER, "MCP_OAUTH_CLIENT_SECRET", "")
    assert await provider.get_client(CLIENT_ID) is None


async def test_authorize_rejects_missing_pkce(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    from mcp.server.auth.provider import AuthorizeError

    client = await provider.get_client(CLIENT_ID)
    with pytest.raises(AuthorizeError):
        await provider.authorize(client, _params(code_challenge=""))


async def test_authorize_rejects_plain_pkce(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    from mcp.server.auth.provider import AuthorizeError

    client = await provider.get_client(CLIENT_ID)
    params = _params()
    plain = SimpleNamespace(
        state=params.state,
        scopes=params.scopes,
        code_challenge=params.code_challenge,
        code_challenge_method="plain",
        redirect_uri=params.redirect_uri,
        redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
        resource=params.resource,
    )
    with pytest.raises(AuthorizeError):
        await provider.authorize(client, plain)


async def test_expired_refresh_rejected(dbSession, monkeypatch):
    import time

    from mcp.server.auth.provider import RefreshToken, TokenError

    provider = _use_test_env(monkeypatch, dbSession)
    client = await provider.get_client(CLIENT_ID)
    expired = RefreshToken(
        token="expired-refresh-value",
        client_id=CLIENT_ID,
        scopes=["wallet"],
        expires_at=int(time.time()) - 10,
        resource=None,
        subject="1",
    )
    provider.refreshTokens[expired.token] = expired
    provider.refreshSessions[expired.token] = "sess"
    with pytest.raises(TokenError) as exc:
        await provider.exchange_refresh_token(client, expired, [])
    assert exc.value.error == "invalid_grant"


async def test_revoked_session_access_fails(dbSession, monkeypatch):
    provider = _use_test_env(monkeypatch, dbSession)
    userId, sessionId = _seed_user(dbSession)
    token = createAccessToken({"userId": str(userId), "sessionId": sessionId})
    assert await provider.load_access_token(token) is not None
    assert SessionManager.revokeSession(dbSession, sessionId, userId)
    assert await provider.load_access_token(token) is None


def _http_app():
    from main.controller.wallet_controller import walletMcp

    return walletMcp.http_app(path="/", transport="streamable-http", stateless_http=True)


def _authorize_request_id(client):
    response = client.get(
        "/authorize",
        params={
            "response_type": "code",
            "client_id": CLIENT_ID,
            "redirect_uri": REDIRECT_URI,
            "code_challenge": CHALLENGE,
            "code_challenge_method": "S256",
            "state": "xyz",
            "scope": "wallet",
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    return parse_qs(urlparse(response.headers["location"]).query)["request_id"][0]


def _login_post(client, requestId, username="oauthuser", password="correct-horse-9"):
    response = client.post(
        f"/oauth/login?request_id={requestId}",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    # The session cookie is Secure (prod parity): httpx's jar drops Secure
    # cookies on http, so propagate it explicitly like a browser on localhost.
    raw = response.headers.get("set-cookie", "")
    for part in raw.split(";"):
        if part.strip().startswith("mansa_token="):
            client.cookies.set("mansa_token", part.strip().split("=", 1)[1].strip('"'))
    return response


def _token_post(client, data):
    return client.post("/token", data=data)


def test_issuer_advertises_public_base(dbSession, monkeypatch):
    """RFC 8414 §3.3: metadata issuer must equal the public origin clients fetch from."""
    _use_test_env(monkeypatch, dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        meta = httpClient.get("/.well-known/oauth-authorization-server")
        assert meta.status_code == 200, meta.text
        body = meta.json()
        public = Config.USER.MCP_PUBLIC_BASE_URL.rstrip("/")
        assert body["issuer"] == f"{public}/"
        assert str(body["authorization_endpoint"]).startswith(public)
        assert str(body["token_endpoint"]).startswith(public)


def test_http_no_session_shows_login_form(dbSession, monkeypatch):
    _use_test_env(monkeypatch, dbSession)
    _seed_user(dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        requestId = _authorize_request_id(httpClient)
        page = httpClient.get(f"/oauth/login?request_id={requestId}")
        assert page.status_code == 200
        assert "<form" in page.text and "password" in page.text


def test_http_full_flow_token_refresh_revoke(dbSession, monkeypatch):
    _use_test_env(monkeypatch, dbSession)
    _seed_user(dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        requestId = _authorize_request_id(httpClient)
        login = _login_post(httpClient, requestId)
        assert login.status_code == 302
        code = parse_qs(urlparse(login.headers["location"]).query)["code"][0]

        tokenBody = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code_verifier": VERIFIER,
        }
        first = _token_post(httpClient, tokenBody)
        assert first.status_code == 200, first.text
        firstTokens = first.json()
        assert firstTokens["scope"] == "wallet" and firstTokens["refresh_token"]

        reuse = _token_post(httpClient, tokenBody)
        assert reuse.status_code == 401 and "invalid_grant" in reuse.text

        refreshed = _token_post(
            httpClient,
            {
                "grant_type": "refresh_token",
                "refresh_token": firstTokens["refresh_token"],
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
        assert refreshed.status_code == 200, refreshed.text
        secondTokens = refreshed.json()
        assert secondTokens["refresh_token"] != firstTokens["refresh_token"]

        staleRefresh = _token_post(
            httpClient,
            {
                "grant_type": "refresh_token",
                "refresh_token": firstTokens["refresh_token"],
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
            },
        )
        assert staleRefresh.status_code == 401 and "invalid_grant" in staleRefresh.text

        revoke = httpClient.post(
            "/revoke",
            data={"token": secondTokens["access_token"], "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        )
        assert revoke.status_code == 200
        assert solo.soloProvider.codes == {}


def test_http_pkce_mismatch_and_wrong_secret(dbSession, monkeypatch):
    _use_test_env(monkeypatch, dbSession)
    _seed_user(dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        requestId = _authorize_request_id(httpClient)
        code = parse_qs(urlparse(_login_post(httpClient, requestId).headers["location"]).query)["code"][0]
        bad = _token_post(
            httpClient,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code_verifier": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
            },
        )
        # FastMCP's OAuth 2.1 token handler surfaces grant failures (bad code,
        # PKCE mismatch) as 401 invalid_grant and bad secrets as 401 invalid_client.
        assert bad.status_code == 401 and "invalid_grant" in bad.text

        requestId = _authorize_request_id(httpClient)
        page = httpClient.get(f"/oauth/login?request_id={requestId}", follow_redirects=False)
        assert page.status_code == 302
        code = parse_qs(urlparse(page.headers["location"]).query)["code"][0]
        wrongSecret = _token_post(
            httpClient,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": "nope",
                "code_verifier": VERIFIER,
            },
        )
        assert wrongSecret.status_code == 401 and "invalid_client" in wrongSecret.text


def test_http_session_cookie_resumes_login(dbSession, monkeypatch):
    _use_test_env(monkeypatch, dbSession)
    _seed_user(dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        requestId = _authorize_request_id(httpClient)
        assert _login_post(httpClient, requestId).status_code == 302
        secondId = _authorize_request_id(httpClient)
        resume = httpClient.get(f"/oauth/login?request_id={secondId}", follow_redirects=False)
        assert resume.status_code == 302
        assert "code=" in resume.headers["location"]


def test_http_bearer_mcp_call_refresh_revoke_cycle(dbSession, monkeypatch):
    """OpenCode-shaped E2E: token -> Bearer MCP call -> refresh still works -> revoke kills access."""
    _use_test_env(monkeypatch, dbSession)
    userId, _ = _seed_user(dbSession)
    wallet = WalletsManager.getMyWallet(dbSession, userId)
    EntriesManager.addEntry(
        dbSession,
        wallet,
        EntryCreate(side="Compra", asset_type="ACOES", ticker="PETR4", date=date(2026, 1, 2), quantity=10, price=10.0),
    )
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        requestId = _authorize_request_id(httpClient)
        code = parse_qs(urlparse(_login_post(httpClient, requestId).headers["location"]).query)["code"][0]
        tokens = _token_post(
            httpClient,
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code_verifier": VERIFIER,
            },
        ).json()
        bearer = {"Authorization": f"Bearer {tokens['access_token']}"}

        anonymous = httpClient.post(
            "/",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "t", "version": "1"},
                },
            },
            headers={"Accept": "application/json, text/event-stream"},
        )
        assert anonymous.status_code == 401

        call = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "wallet_positions", "arguments": {"authorization": f"Bearer {tokens['access_token']}"}},
        }
        authed = httpClient.post("/", json=call, headers={"Accept": "application/json, text/event-stream", **bearer})
        assert authed.status_code == 200, authed.text
        assert "PETR4" in authed.text

        httpClient.post(
            "/revoke", data={"token": tokens["access_token"], "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET}
        )
        after = httpClient.post("/", json=call, headers={"Accept": "application/json, text/event-stream", **bearer})
        assert "401" in after.text


def test_prm_resource_has_no_trailing_slash(dbSession, monkeypatch):
    """RFC 9728 exact-match: PRM resource == canonical publicMcpUrl (no slash)."""
    _use_test_env(monkeypatch, dbSession)
    with TestClient(_http_app(), raise_server_exceptions=False) as httpClient:
        meta = httpClient.get("/.well-known/oauth-protected-resource/wallet/mcp", follow_redirects=False)
        assert meta.status_code == 200, meta.text
        assert meta.json()["resource"] == solo.publicMcpUrl()
        assert not meta.json()["resource"].endswith("/")
