"""F-A audit tests: controller fixes — CSRF patch removal, SSO suffix-unique, generic 400s, login eviction, introspect gate, PII scrub."""

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from config import getSession
from main.app.authentication.authentication import AuthenticationManager
from main.app.authentication.session import SessionManager
from main.controller.authentication_controller import router as authRouter
from main.models.user import User
from main.utils.errors import registerErrorHandlers

SERVICE_HEADERS = {"X-Service-Token": "test-service-token"}


@pytest.fixture(autouse=True)
def serviceToken(monkeypatch):
    monkeypatch.setenv("INTROSPECT_SERVICE_TOKEN", "test-service-token")


@pytest.fixture
def authDbClient(dbSession):
    app = FastAPI()
    app.include_router(authRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[getSession] = lambda: dbSession
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def makeAccount(dbSession, username, email=None, password="secret123", googleId=None):
    AuthenticationManager.createUserAccount(
        dbSession, username=username, email=email or f"{username}@example.com", password=password, googleId=googleId
    )
    return AuthenticationManager.authenticateUser(dbSession, username, password) if password else None


def mockSSO(userId="google-new-1", email="newuser@gmail.com"):
    sso = AsyncMock()
    sso.__aenter__ = AsyncMock(return_value=sso)
    sso.__aexit__ = AsyncMock(return_value=False)
    info = MagicMock()
    info.id = userId
    info.email = email
    sso.verify_and_process = AsyncMock(return_value=info)
    return sso


class TestCallbackNoCookiePatch:
    def test_callback_without_sso_state_cookie(self, dbSession, authDbClient):
        seen = {}

        async def fake_verify(request):
            seen.update(request.cookies)
            return mockSSO().verify_and_process.return_value

        info = MagicMock()
        info.id = "google-nocookie-1"
        info.email = "nocookie@gmail.com"

        async def fake_verify2(request):
            seen.update(request.cookies)
            return info

        with patch("main.controller.authentication_controller.getGoogleSSO") as g:
            sso = AsyncMock()
            sso.__aenter__ = AsyncMock(return_value=sso)
            sso.__aexit__ = AsyncMock(return_value=False)
            sso.verify_and_process = fake_verify2
            g.return_value = sso
            resp = authDbClient.get("/auth/callback?state=x&code=c", follow_redirects=False)
        assert resp.status_code == 200
        assert "sso_state" not in seen


class TestSSOSuffixUnique:
    def _sso(self, googleId, email):
        sso = AsyncMock()
        sso.__aenter__ = AsyncMock(return_value=sso)
        sso.__aexit__ = AsyncMock(return_value=False)
        info = MagicMock()
        info.id = googleId
        info.email = email
        sso.verify_and_process = AsyncMock(return_value=info)
        return sso

    def _callback(self, authDbClient, email, googleId):
        with patch("main.controller.authentication_controller.getGoogleSSO", return_value=self._sso(googleId, email)):
            return authDbClient.get("/auth/callback?state=not-a-url&code=c", follow_redirects=False)

    def test_first_collision_gets_suffix_1(self, dbSession, authDbClient):
        dbSession.add(User(username="alice", email="alice@other.com", passwordHash="h", roles="USER"))
        dbSession.commit()
        resp = self._callback(authDbClient, "alice@gmail.com", "google-alice-1")
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "alice1"

    def test_second_collision_gets_suffix_2(self, dbSession, authDbClient):
        dbSession.add(User(username="alice", email="alice@other.com", passwordHash="h", roles="USER"))
        dbSession.add(User(username="alice1", email="alice1@other.com", passwordHash="h", roles="USER"))
        dbSession.commit()
        resp = self._callback(authDbClient, "alice@gmail.com", "google-alice-2")
        assert resp.status_code == 200
        assert resp.json()["user"]["username"] == "alice2"


class TestRegisterGeneric400:
    def test_colliding_username(self, dbSession, authDbClient):
        makeAccount(dbSession, "bob", "bob@example.com")
        resp = authDbClient.post(
            "/auth/register", json={"username": "bob", "email": "other@example.com", "password": "secret123"}
        )
        assert resp.status_code == 400
        text = resp.text.lower()
        assert "registration failed." in text
        assert "already" not in text

    def test_colliding_email(self, dbSession, authDbClient):
        makeAccount(dbSession, "bob2", "bob2@example.com")
        resp = authDbClient.post(
            "/auth/register", json={"username": "someone", "email": "bob2@example.com", "password": "secret123"}
        )
        assert resp.status_code == 400
        text = resp.text.lower()
        assert "registration failed." in text
        assert "already" not in text


class TestLoginRevokesOthers:
    def test_old_session_deactivated(self, dbSession, authDbClient, monkeypatch):
        makeAccount(dbSession, "carol", "carol@example.com")
        user = AuthenticationManager.authenticateUser(dbSession, "carol", "secret123")
        old = SessionManager.createSession(dbSession, user["userId"], "pytest")

        calls = {}
        real = SessionManager.revokeAllExcept

        def recording(db, user_id, keep_session_id):
            calls["args"] = (user_id, keep_session_id)
            return real(db, user_id, keep_session_id)

        monkeypatch.setattr(SessionManager, "revokeAllExcept", recording)
        resp = authDbClient.post("/auth/login", json={"username": "carol", "password": "secret123"})
        assert resp.status_code == 200
        assert calls["args"][0] == user["userId"]
        assert calls["args"][1] != old.sessionId
        dbSession.refresh(old)
        assert old.isActive is False
        kept = SessionManager.getSessionById(dbSession, calls["args"][1], user["userId"])
        assert kept is not None and kept.isActive is True


class TestIntrospectGate:
    def _token(self, dbSession):
        makeAccount(dbSession, "dave", "dave@example.com")
        user = AuthenticationManager.authenticateUser(dbSession, "dave", "secret123")
        session = SessionManager.createSession(dbSession, user["userId"], "pytest")
        from main.app.authentication.util import createAccessToken

        return createAccessToken({"userId": str(user["userId"]), "sessionId": session.sessionId})

    def test_no_header_401(self, authDbClient):
        resp = authDbClient.post("/auth/introspect", json={"token": "x"})
        assert resp.status_code == 401

    def test_wrong_header_401(self, authDbClient):
        resp = authDbClient.post("/auth/introspect", json={"token": "x"}, headers={"X-Service-Token": "wrong"})
        assert resp.status_code == 401

    def test_valid_token_with_header_200(self, dbSession, authDbClient):
        token = self._token(dbSession)
        resp = authDbClient.post("/auth/introspect", json={"token": token}, headers=SERVICE_HEADERS)
        assert resp.status_code == 200

    def test_invalid_token_generic_401(self, authDbClient):
        resp = authDbClient.post("/auth/introspect", json={"token": "bad"}, headers=SERVICE_HEADERS)
        body = resp.json()
        assert resp.status_code == 401
        assert "Unauthorized" in body.get("error", "")
        for leaked in ("expired", "Invalid token", "revoked"):
            assert leaked not in resp.text


class TestSSORevokesOthers:
    def _sso(self, googleId, email):
        sso = AsyncMock()
        sso.__aenter__ = AsyncMock(return_value=sso)
        sso.__aexit__ = AsyncMock(return_value=False)
        info = MagicMock()
        info.id = googleId
        info.email = email
        sso.verify_and_process = AsyncMock(return_value=info)
        return sso

    def test_attacker_session_killed_new_survives(self, dbSession, authDbClient):
        AuthenticationManager.createUserAccount(
            dbSession, username="ssouser", email="ssouser@gmail.com", googleId="google-victim-1"
        )
        user = AuthenticationManager.authenticateGoogleUser(dbSession, "google-victim-1")
        attacker = SessionManager.createSession(dbSession, user["userId"], "attacker-agent")

        with patch(
            "main.controller.authentication_controller.getGoogleSSO",
            return_value=self._sso("google-victim-1", "ssouser@gmail.com"),
        ):
            resp = authDbClient.get("/auth/callback?state=not-a-url&code=c", follow_redirects=False)

        assert resp.status_code == 200
        dbSession.refresh(attacker)
        assert attacker.isActive is False
        from main.app.authentication.util import verifyAccessToken

        payload = verifyAccessToken(resp.json()["accessToken"])
        kept = SessionManager.getSessionById(dbSession, payload["sessionId"], user["userId"])
        assert kept is not None and kept.isActive is True
        assert kept.sessionId != attacker.sessionId


class TestSecureFlagNotSpoofable:
    def test_spoofed_forwarded_proto_http_keeps_secure(self, dbSession):
        # https_only=True on SessionMiddleware + Secure auth cookies mean the
        # http TestClient cannot round-trip Secure cookies, so assert on the
        # Set-Cookie header instead.
        app = FastAPI()
        app.include_router(authRouter)
        registerErrorHandlers(app)
        app.dependency_overrides[getSession] = lambda: dbSession
        makeAccount(dbSession, "secureguy", "secureguy@example.com")
        with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as httpsClient:
            resp = httpsClient.post(
                "/auth/login",
                json={"username": "secureguy", "password": "secret123"},
                headers={"X-Forwarded-Proto": "http"},
            )
        assert resp.status_code == 200
        assert "secure" in resp.headers.get("set-cookie", "").lower()

    @staticmethod
    def appLogs(caplog):
        # App must not log PII itself; httpx client-side request lines (test-only
        # artifact; in prod this is access-log territory) are out of scope.
        return "\n".join(r.getMessage() for r in caplog.records if r.name.startswith("main."))

    def test_register_logs_no_email(self, dbSession, authDbClient, caplog):
        with caplog.at_level("INFO"):
            authDbClient.post(
                "/auth/register",
                json={"username": "erin", "email": "erin-private@example.com", "password": "secret123"},
            )
        assert "erin-private@example.com" not in self.appLogs(caplog)

    def test_google_logs_no_secret(self, authDbClient, caplog):
        secret = "http://localhost:3000/secret-path-xyz"
        sso = AsyncMock()
        sso.__aenter__ = AsyncMock(return_value=sso)
        sso.__aexit__ = AsyncMock(return_value=False)
        from starlette.responses import RedirectResponse

        sso.get_login_redirect = AsyncMock(
            return_value=RedirectResponse("https://accounts.google.com/x", status_code=303)
        )
        with caplog.at_level("INFO"):
            with patch("main.controller.authentication_controller.getGoogleSSO", return_value=sso):
                authDbClient.get(f"/auth/google?redirect_url={secret}", follow_redirects=False)
        assert "secret-path-xyz" not in self.appLogs(caplog)

    def test_callback_logs_no_email_or_state(self, dbSession, authDbClient, caplog):
        secret_state = "http://localhost:3000/state-secret-abc"
        sso = AsyncMock()
        sso.__aenter__ = AsyncMock(return_value=sso)
        sso.__aexit__ = AsyncMock(return_value=False)
        info = MagicMock()
        info.id = "google-log-1"
        info.email = "logsecret@gmail.com"
        sso.verify_and_process = AsyncMock(return_value=info)
        with caplog.at_level("INFO"):
            with patch("main.controller.authentication_controller.getGoogleSSO", return_value=sso):
                authDbClient.get(f"/auth/callback?state={secret_state}&code=c", follow_redirects=False)
        assert "logsecret@gmail.com" not in self.appLogs(caplog)
        assert "state-secret-abc" not in self.appLogs(caplog)
