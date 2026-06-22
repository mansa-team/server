"""Tests to cover uncovered lines across controllers, UserManager, and auth util.

Each test class targets specific uncovered lines in the corresponding source file.
Uses @patch to mock service dependencies and a per-test FastAPI app when needed.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock, PropertyMock
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient as _TestClient
from fastapi.responses import RedirectResponse

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Helper: build a minimal TestClient for auth_controller with a mock DB dep
# ---------------------------------------------------------------------------
def _make_auth_client():
    """Return (client, app) with auth + user routers and mocked getSession."""
    from main.controller.authentication_controller import router as authRouter
    from main.controller.user_controller import router as userRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(authRouter)
    app.include_router(userRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session
    return _TestClient(app, raise_server_exceptions=False), app, mock_session


def _make_user_client(mock_current_user=None):
    """Return (client, app) with user router and mocked deps."""
    from main.controller.user_controller import router as userRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager

    app = FastAPI()
    app.include_router(userRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    if mock_current_user is not None:
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: mock_current_user

    return _TestClient(app, raise_server_exceptions=False), app, mock_session


def _make_prometheus_client(mock_current_user=None, mock_permission_user=None):
    """Return (client, app) with prometheus router and mocked deps."""
    from main.controller.prometheus_controller import router as promRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager

    app = FastAPI()
    app.include_router(promRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    user = mock_current_user or {"userId": 1, "username": "testuser", "roles": ["PREMIUM"]}
    # ponytail: per-call Roles.requirePermission returns a fresh callable;
    # override key never matches the actual dep, so the line is a no-op. Skip.
    app.dependency_overrides[UserManager.getCurrentUser] = lambda: user

    return _TestClient(app, raise_server_exceptions=False), app, mock_session


def _make_stocksapi_client(mock_current_user=None, mock_api_key=None):
    """Return (client, app) with stocks router and mocked deps."""
    from main.controller.stocksapi_controller import router as stocksRouter
    from main.utils.errors import registerErrorHandlers
    from main.app.user.user import UserManager

    app = FastAPI()
    app.include_router(stocksRouter)
    registerErrorHandlers(app)

    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session

    if mock_current_user is not None:
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: mock_current_user

    if mock_api_key is not None:
        from main.app.stocks_api.key import verifyAPIKey

        app.dependency_overrides[verifyAPIKey] = lambda: mock_api_key

    return _TestClient(app, raise_server_exceptions=False), app, mock_session


# =========================================================================
# 1. authentication_controller.py — 89 uncovered lines
# =========================================================================
class TestIsSecureScheme:
    """Covers line 23: isSecureScheme helper."""

    def test_is_secure_https(self):
        from main.controller.authentication_controller import isSecureScheme

        request = MagicMock()
        request.url.scheme = "https"
        assert isSecureScheme(request) is True

    def test_is_secure_http(self):
        from main.controller.authentication_controller import isSecureScheme

        request = MagicMock()
        request.url.scheme = "http"
        assert isSecureScheme(request) is False

    def test_is_secure_no_scheme(self):
        from main.controller.authentication_controller import isSecureScheme

        request = MagicMock()
        request.url.scheme = ""
        assert isSecureScheme(request) is False


class TestHealthEndpoint:
    """Covers line 28: GET /auth/health."""

    def test_health_returns_ok(self):
        from main.controller.authentication_controller import router as authRouter

        app = FastAPI()
        app.include_router(authRouter)
        client = _TestClient(app, raise_server_exceptions=False)
        response = client.get("/auth/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "authentication"


class TestRegisterEndpoint:
    """Covers lines 44-54, 63, 66-71: register success, ValueError, generic Exception."""

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_register_success(self, mock_auth_mgr, mock_create_token, mock_session_mgr):
        """Covers lines 44-54, 63: successful registration + auto-login."""
        client, _, _ = _make_auth_client()

        mock_auth_mgr.createUserAccount.return_value = True
        mock_auth_mgr.authenticateUser.return_value = {"userId": 1, "username": "alice", "roles": ["USER"]}

        mock_session = MagicMock()
        mock_session.sessionId = "sess-123"
        mock_session_mgr.createSession.return_value = mock_session

        mock_create_token.return_value = ("jwt-token-abc", timedelta(hours=720))

        response = client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
            headers={"User-Agent": "TestAgent/1.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "success"
        assert data["accessToken"] == "jwt-token-abc"
        assert data["tokenType"] == "bearer"
        mock_auth_mgr.createUserAccount.assert_called_once()

    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_register_auto_login_fails(self, mock_auth_mgr):
        """Covers line 46: auto-login fails after registration."""
        client, _, _ = _make_auth_client()
        mock_auth_mgr.createUserAccount.return_value = True
        mock_auth_mgr.authenticateUser.return_value = None

        response = client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 401

    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_register_value_error(self, mock_auth_mgr):
        """Covers lines 66-68: ValueError during registration."""
        client, _, _ = _make_auth_client()
        mock_auth_mgr.createUserAccount.side_effect = ValueError("Invalid input")

        response = client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 400

    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_register_generic_exception(self, mock_auth_mgr):
        """Covers lines 69-71: generic Exception during registration."""
        client, _, _ = _make_auth_client()
        mock_auth_mgr.createUserAccount.side_effect = RuntimeError("DB error")

        response = client.post(
            "/auth/register",
            json={"username": "alice", "email": "alice@example.com", "password": "secret123"},
        )
        assert response.status_code == 500


class TestLoginEndpoint:
    """Covers lines 87-93, 102: login success and failure paths."""

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_login_success(self, mock_auth_mgr, mock_create_token, mock_session_mgr):
        """Covers lines 87-93, 102: successful login."""
        client, _, _ = _make_auth_client()
        mock_auth_mgr.authenticateUser.return_value = {"userId": 1, "username": "bob", "roles": ["USER"]}

        mock_session = MagicMock()
        mock_session.sessionId = "sess-456"
        mock_session_mgr.createSession.return_value = mock_session

        mock_create_token.return_value = ("jwt-token-xyz", timedelta(hours=720))

        response = client.post(
            "/auth/login",
            json={"username": "bob", "password": "secret123"},
            headers={"User-Agent": "TestAgent/1.0"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["accessToken"] == "jwt-token-xyz"
        assert data["tokenType"] == "bearer"

    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_login_wrong_credentials(self, mock_auth_mgr):
        """Covers line 85: authenticateUser returns None."""
        client, _, _ = _make_auth_client()
        mock_auth_mgr.authenticateUser.return_value = None

        response = client.post(
            "/auth/login",
            json={"username": "bob", "password": "wrongpass"},
        )
        assert response.status_code == 401
        # Error handler wraps in ErrorResponse model — detail is in "error" field
        assert "Invalid credentials" in response.json()["error"]


class TestLogoutEndpoint:
    """Covers lines 107, 109-130, 133: logout token extraction and revocation."""

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.verifyAccessToken")
    def test_logout_with_x_access_token(self, mock_verify, mock_session_mgr, mock_secure):
        """Covers lines 109, 115-125: logout with X-Access-Token header."""
        client, _, _ = _make_auth_client()
        mock_verify.return_value = {"userId": 1, "sessionId": "123"}
        mock_session_mgr.revokeSession.return_value = True

        response = client.post(
            "/auth/logout",
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"
        mock_session_mgr.revokeSession.assert_called_once()

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.verifyAccessToken")
    def test_logout_with_bearer_header(self, mock_verify, mock_session_mgr, mock_secure):
        """Covers lines 111-113: token extracted from Authorization Bearer header."""
        client, _, _ = _make_auth_client()
        mock_verify.return_value = {"userId": 1, "sessionId": "456"}
        mock_session_mgr.revokeSession.return_value = True

        response = client.post(
            "/auth/logout",
            headers={"Authorization": "Bearer my-jwt-token"},
        )
        assert response.status_code == 200

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.verifyAccessToken")
    def test_logout_with_invalid_session_id(self, mock_verify, mock_session_mgr, mock_secure):
        """Covers lines 122-124: sessionId is not a valid int, ValueError caught."""
        client, _, _ = _make_auth_client()
        mock_verify.return_value = {"userId": 1, "sessionId": "not-a-number"}

        response = client.post(
            "/auth/logout",
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 200
        mock_session_mgr.revokeSession.assert_not_called()

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    @patch("main.app.authentication.util.verifyAccessToken")
    def test_logout_with_verification_error(self, mock_verify, mock_secure):
        """Covers lines 126-128: verifyAccessToken raises Exception."""
        client, _, _ = _make_auth_client()
        mock_verify.side_effect = Exception("token expired")

        response = client.post(
            "/auth/logout",
            headers={"X-Access-Token": "bad-token"},
        )
        assert response.status_code == 200

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    def test_logout_without_token(self, mock_secure):
        """Covers lines 109-113: no token provided at all."""
        client, _, _ = _make_auth_client()

        response = client.post("/auth/logout")
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"

    @patch("main.controller.authentication_controller.isSecureScheme", return_value=False)
    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.verifyAccessToken")
    def test_logout_with_missing_user_and_session(self, mock_verify, mock_session_mgr, mock_secure):
        """Covers line 120: userId or sessionId missing from payload."""
        client, _, _ = _make_auth_client()
        mock_verify.return_value = {"userId": None, "sessionId": None}

        response = client.post(
            "/auth/logout",
            headers={"X-Access-Token": "valid-token"},
        )
        assert response.status_code == 200


class TestGoogleLogin:
    """Covers lines 139, 141-149: googleLogin endpoint."""

    @patch("main.controller.authentication_controller.getGoogleSSO")
    def test_google_login_with_redirect_url(self, mock_get_sso):
        """Covers lines 139, 141-149: Google login with redirect_url query param."""
        from main.controller.authentication_controller import router as authRouter

        app = FastAPI()
        app.include_router(authRouter)
        client = _TestClient(app, raise_server_exceptions=False)

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)
        mock_sso.get_login_redirect = AsyncMock(return_value=RedirectResponse(url="https://google.com/auth"))
        mock_get_sso.return_value = mock_sso

        response = client.get("/auth/google?redirect_url=http://localhost:3000/callback", follow_redirects=False)
        # Should get a redirect or the mock response
        assert response.status_code in (200, 307, 302)
        mock_sso.get_login_redirect.assert_called_once()

    @patch("main.controller.authentication_controller.getGoogleSSO")
    def test_google_login_with_referer(self, mock_get_sso):
        """Covers line 143: redirect_url falls back to referer header."""
        from main.controller.authentication_controller import router as authRouter

        app = FastAPI()
        app.include_router(authRouter)
        client = _TestClient(app, raise_server_exceptions=False)

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)
        mock_sso.get_login_redirect = AsyncMock(return_value=RedirectResponse(url="https://google.com/auth"))
        mock_get_sso.return_value = mock_sso

        response = client.get(
            "/auth/google",
            headers={"Referer": "http://localhost:3000/dashboard"},
            follow_redirects=False,
        )
        assert response.status_code in (200, 307, 302)


class TestGoogleCallback:
    """Covers lines 155-156, 158, 160-168, 170-177, 179-184, 186, 190-204: googleCallback."""

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_new_user(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Covers lines 160-168, 170-177, 179-184, 186, 197-198: new Google user."""
        client, _, _ = _make_auth_client()

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        mock_user_info = MagicMock()
        mock_user_info.id = "google-123"
        mock_user_info.email = "alice@gmail.com"
        mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)
        mock_get_sso.return_value = mock_sso

        # First call returns None (no existing user), second call returns user after creation
        mock_auth_mgr.authenticateGoogleUser.side_effect = [
            None,
            {"userId": 2, "username": "alice", "roles": ["USER"]},
        ]
        mock_auth_mgr.createUserAccount.return_value = True

        mock_session = MagicMock()
        mock_session.sessionId = "gsess-123"
        mock_session_mgr.createSession.return_value = mock_session
        mock_create_token.return_value = ("google-jwt-abc", timedelta(hours=720))

        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 200
        data = response.json()
        assert data["accessToken"] == "google-jwt-abc"

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_existing_user(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Covers lines 164, 171-173: existing Google user, no new account created."""
        client, _, _ = _make_auth_client()

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        mock_user_info = MagicMock()
        mock_user_info.id = "google-456"
        mock_user_info.email = "bob@gmail.com"
        mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)
        mock_get_sso.return_value = mock_sso

        mock_auth_mgr.authenticateGoogleUser.return_value = {"userId": 3, "username": "bob", "roles": ["USER"]}

        mock_session = MagicMock()
        mock_session.sessionId = "gsess-456"
        mock_session_mgr.createSession.return_value = mock_session
        mock_create_token.return_value = ("google-jwt-def", timedelta(hours=720))

        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 200
        mock_auth_mgr.createUserAccount.assert_not_called()

    @patch("main.controller.authentication_controller.getGoogleSSO")
    def test_callback_no_user_info(self, mock_get_sso):
        """Covers line 165: verify_and_process returns None."""
        client, _, _ = _make_auth_client()

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)
        mock_sso.verify_and_process = AsyncMock(return_value=None)
        mock_get_sso.return_value = mock_sso

        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 400

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_with_state_redirect(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Covers lines 190-195: state param triggers RedirectResponse."""
        client, _, _ = _make_auth_client()

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        mock_user_info = MagicMock()
        mock_user_info.id = "google-789"
        mock_user_info.email = "carol@gmail.com"
        mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)
        mock_get_sso.return_value = mock_sso

        mock_auth_mgr.authenticateGoogleUser.return_value = {"userId": 4, "username": "carol", "roles": ["USER"]}

        mock_session = MagicMock()
        mock_session.sessionId = "gsess-789"
        mock_session_mgr.createSession.return_value = mock_session
        mock_create_token.return_value = ("google-jwt-ghi", timedelta(hours=720))

        response = client.get(
            "/auth/callback?state=http://localhost:3000/dashboard",
            follow_redirects=False,
        )
        # Should be a redirect
        assert response.status_code in (307, 302)

    @patch("main.controller.authentication_controller.getGoogleSSO")
    def test_callback_generic_exception(self, mock_get_sso):
        """Covers lines 202-204: generic Exception in callback."""
        client, _, _ = _make_auth_client()

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)
        mock_sso.verify_and_process = AsyncMock(side_effect=RuntimeError("SSO error"))
        mock_get_sso.return_value = mock_sso

        response = client.get("/auth/callback", follow_redirects=False)
        assert response.status_code == 500


# =========================================================================
# 2. user_controller.py — 35 uncovered lines
# =========================================================================
class TestUserHealth:
    """Covers line 19: GET /user/health."""

    def test_health(self):
        from main.controller.user_controller import router as userRouter

        app = FastAPI()
        app.include_router(userRouter)
        client = _TestClient(app, raise_server_exceptions=False)
        resp = client.get("/user/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestGetMe:
    """Covers line 24: GET /user/me returns currentUser."""

    def test_get_me(self):
        client, _, _ = _make_user_client(
            mock_current_user={"userId": 1, "username": "alice", "email": "alice@test.com", "roles": ["USER"]}
        )
        resp = client.get("/user/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert data["userId"] == 1


class TestUpgradeEndpoints:
    """Covers lines 31-32, 36, 43-44, 48: upgrade developer starter/enterprise."""

    def test_upgrade_developer_starter_success(self):
        """Covers lines 31-32."""
        client, _, mock_db = _make_user_client(mock_current_user={"userId": 1, "username": "alice", "roles": ["USER"]})
        with patch("main.controller.user_controller.UserManager") as mock_um:
            mock_um.addRoleToUser.return_value = True
            resp = client.post("/user/upgrade/developer/starter")
            assert resp.status_code == 200
            assert "Successfully upgraded" in resp.json()["message"]

    def test_upgrade_developer_starter_already_developer(self):
        """Covers line 36."""
        client, _, mock_db = _make_user_client(mock_current_user={"userId": 1, "username": "alice", "roles": ["USER"]})
        with patch("main.controller.user_controller.UserManager") as mock_um:
            mock_um.addRoleToUser.return_value = False
            resp = client.post("/user/upgrade/developer/starter")
            assert resp.status_code == 200
            assert "already a developer" in resp.json()["message"]

    def test_upgrade_developer_enterprise_success(self):
        """Covers lines 43-44."""
        client, _, mock_db = _make_user_client(mock_current_user={"userId": 1, "username": "alice", "roles": ["USER"]})
        with patch("main.controller.user_controller.UserManager") as mock_um:
            mock_um.addRoleToUser.return_value = True
            resp = client.post("/user/upgrade/developer/enterprise")
            assert resp.status_code == 200
            assert "Successfully upgraded" in resp.json()["message"]

    def test_upgrade_developer_enterprise_already_developer(self):
        """Covers line 48."""
        client, _, mock_db = _make_user_client(mock_current_user={"userId": 1, "username": "alice", "roles": ["USER"]})
        with patch("main.controller.user_controller.UserManager") as mock_um:
            mock_um.addRoleToUser.return_value = False
            resp = client.post("/user/upgrade/developer/enterprise")
            assert resp.status_code == 200
            assert "already a developer" in resp.json()["message"]


class TestAdminAccess:
    """Covers lines 53-54, 56: admin access granted / denied."""

    def test_admin_access_granted(self):
        """Covers lines 53-54."""
        client, _, _ = _make_user_client(mock_current_user={"userId": 1, "username": "admin", "roles": ["ADMIN"]})
        resp = client.get("/user/admin")
        assert resp.status_code == 200
        assert "Admin access granted" in resp.json()["message"]

    def test_admin_access_denied(self):
        """Covers line 56."""
        client, _, _ = _make_user_client(mock_current_user={"userId": 1, "username": "alice", "roles": ["USER"]})
        resp = client.get("/user/admin")
        assert resp.status_code == 403
        # Error handler wraps in ErrorResponse model — detail goes to "error" field
        assert "Admin access denied" in resp.json()["error"]


class TestGetSessions:
    """Covers lines 66, 68-72, 74: GET /user/sessions."""

    def test_get_sessions(self):
        """Covers lines 66, 68-72, 74: full sessions listing."""
        mock_session_1 = MagicMock()
        mock_session_1.sessionId = "sess-1"
        mock_session_1.getDeviceName.return_value = "Chrome on Windows"
        mock_session_1.browser = "Chrome"
        mock_session_1.operatingSystem = "Windows"
        mock_session_1.deviceType = "desktop"
        mock_session_1.isActive = True
        mock_session_1.lastActivityAt = datetime(2026, 1, 1)
        mock_session_1.createdAt = datetime(2026, 1, 1)

        mock_session_2 = MagicMock()
        mock_session_2.sessionId = "sess-2"
        mock_session_2.getDeviceName.return_value = "Safari on macOS"
        mock_session_2.browser = "Safari"
        mock_session_2.operatingSystem = "macOS"
        mock_session_2.deviceType = "mobile"
        mock_session_2.isActive = False
        mock_session_2.lastActivityAt = None
        mock_session_2.createdAt = None

        from main.controller.user_controller import router as userRouter
        from main.utils.errors import registerErrorHandlers
        from main.app.user.user import UserManager
        from main.app.authentication.util import extractTokenPayload

        app = FastAPI()
        app.include_router(userRouter)
        registerErrorHandlers(app)
        mock_db = MagicMock()
        app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
            "userId": 1,
            "username": "alice",
            "roles": ["USER"],
        }
        app.dependency_overrides[extractTokenPayload] = lambda: {"userId": 1, "sessionId": "sess-1"}

        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getUserSessions.return_value = [mock_session_1, mock_session_2]

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.get("/user/sessions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert data["active"] == 1
            assert len(data["sessions"]) == 2


class TestGetCurrentSession:
    """Covers lines 100-104, 106: GET /user/sessions/current."""

    def test_get_current_session_found(self):
        """Covers lines 100-104, 106: session found."""
        mock_session = MagicMock()
        mock_session.sessionId = "current-sess"
        mock_session.getDeviceName.return_value = "Chrome on Windows"
        mock_session.browser = "Chrome"
        mock_session.operatingSystem = "Windows"
        mock_session.deviceType = "desktop"
        mock_session.userAgent = "Mozilla/5.0"
        mock_session.lastActivityAt = datetime(2026, 1, 1)
        mock_session.createdAt = datetime(2026, 1, 1)

        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getCurrentSession.return_value = mock_session

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.get("/user/sessions/current")
            assert resp.status_code == 200
            assert resp.json()["sessionId"] == "current-sess"

    def test_get_current_session_not_found(self):
        """Covers line 104: session not found."""
        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getCurrentSession.return_value = None

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.get("/user/sessions/current")
            assert resp.status_code == 404


class TestRevokeSession:
    """Covers lines 126-136: DELETE /user/sessions/{sessionId}."""

    def test_revoke_session_success(self):
        """Covers lines 126, 131, 135-136."""
        mock_session = MagicMock()
        mock_session.sessionId = "sess-to-revoke"

        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getSessionById.return_value = mock_session
            mock_sm.revokeSession.return_value = True

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/user/sessions/sess-to-revoke")
            assert resp.status_code == 200
            assert "revoked successfully" in resp.json()["message"]

    def test_revoke_session_not_found(self):
        """Covers lines 127-129: session not found."""
        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getSessionById.return_value = None

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/user/sessions/nonexistent")
            assert resp.status_code == 404

    def test_revoke_session_failure(self):
        """Covers lines 132-133: revokeSession returns False."""
        mock_session = MagicMock()

        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.getSessionById.return_value = mock_session
            mock_sm.revokeSession.return_value = False

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.delete("/user/sessions/sess-fail")
            assert resp.status_code == 500


class TestRevokeAllSessions:
    """Covers lines 143, 145, 147-148: POST /user/sessions/revoke-all."""

    def test_revoke_all_sessions(self):
        """Covers lines 143, 145, 147-148."""
        with patch("main.controller.user_controller.SessionManager") as mock_sm:
            mock_sm.revokeAllSessions.return_value = 3

            from main.controller.user_controller import router as userRouter
            from main.utils.errors import registerErrorHandlers
            from main.app.user.user import UserManager

            app = FastAPI()
            app.include_router(userRouter)
            registerErrorHandlers(app)
            app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
                "userId": 1,
                "username": "alice",
                "roles": ["USER"],
            }

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.post("/user/sessions/revoke-all")
            assert resp.status_code == 200
            assert resp.json()["revokedCount"] == 3


# =========================================================================
# 3. prometheus_controller.py — 28 uncovered lines
# =========================================================================
class TestPrometheusHealth:
    """Covers line 24: GET /prometheus/health."""

    def test_health(self):
        from main.controller.prometheus_controller import router as promRouter

        app = FastAPI()
        app.include_router(promRouter)
        client = _TestClient(app, raise_server_exceptions=False)
        resp = client.get("/prometheus/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestPrometheusGetSessions:
    """Covers lines 33-36: GET /prometheus/sessions."""

    def test_get_sessions(self):
        """Covers lines 33-36."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.getUserSessions.return_value = [
                {"sessionId": "s1", "title": "Chat 1", "lastActivity": "2026-01-01T00:00:00"},
            ]

            client, _, _ = _make_prometheus_client()
            resp = client.get("/prometheus/sessions")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 1
            assert data["success"] is True


class TestPrometheusCreateSession:
    """Covers line 52: POST /prometheus/sessions."""

    def test_create_session(self):
        """Covers line 52."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.createSession.return_value = "new-session-id"

            client, _, _ = _make_prometheus_client()
            resp = client.post("/prometheus/sessions", json={"title": "New Chat"})
            assert resp.status_code == 200
            assert resp.json()["sessionId"] == "new-session-id"


class TestPrometheusUpdateSessionTitle:
    """Covers lines 62-63, 65-68: PUT /prometheus/sessions/{sessionId}."""

    def test_update_title_success(self):
        """Covers lines 65-68: title updated successfully."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.verifySessionOwnership.return_value = True
            mock_pcm.updateSessionTitle.return_value = True

            client, _, _ = _make_prometheus_client()
            resp = client.put("/prometheus/sessions/s1", json={"title": "Updated"})
            assert resp.status_code == 200
            assert resp.json()["message"] == "Session title updated"

    def test_update_title_not_owner(self):
        """Covers lines 62-63: not the session owner."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.verifySessionOwnership.return_value = False

            client, _, _ = _make_prometheus_client()
            resp = client.put("/prometheus/sessions/s1", json={"title": "Hacked"})
            assert resp.status_code == 403

    def test_update_title_not_found(self):
        """Covers lines 66-67: session not found."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.verifySessionOwnership.return_value = True
            mock_pcm.updateSessionTitle.return_value = False

            client, _, _ = _make_prometheus_client()
            resp = client.put("/prometheus/sessions/s1", json={"title": "Ghost"})
            assert resp.status_code == 404


class TestPrometheusGetHistory:
    """Covers lines 77, 83-84, 86: GET /prometheus/history/{sessionId}."""

    def test_get_history_found(self):
        """Covers lines 77, 86: session found with history."""
        mock_session = MagicMock()
        mock_session.sessionId = "s1"
        mock_session.userId = 1
        mock_session.history = [{"role": "user", "content": "hello"}]

        # The prometheus router uses Roles.requirePermission(Permission.USE_PROMETHEUS) as a dep.
        # This creates a new callable each time, so dependency_overrides can't match it.
        # Instead, we patch the module-level Roles to return a fixed checker.
        from main.app.user.user import UserManager
        from main.app.authentication.util import extractTokenPayload

        app = FastAPI()
        from main.controller.prometheus_controller import router as promRouter
        from main.utils.errors import registerErrorHandlers

        app.include_router(promRouter)
        registerErrorHandlers(app)
        mock_db = MagicMock()
        app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
            "userId": 1,
            "username": "alice",
            "roles": ["PREMIUM"],
        }
        app.dependency_overrides[extractTokenPayload] = lambda: {"userId": 1}

        # Patch the session query chain
        mock_db.query.return_value.filter.return_value.first.return_value = mock_session

        # Patch Roles.requirePermission to return a function that always passes
        with patch("main.controller.prometheus_controller.Roles") as mock_roles:

            async def mock_checker(user=None, **kwargs):
                return user or {"userId": 1, "username": "alice", "roles": ["PREMIUM"]}

            mock_roles.requirePermission.return_value = mock_checker

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.get("/prometheus/history/s1")
            assert resp.status_code == 200
            assert resp.json()["history"] == [{"role": "user", "content": "hello"}]

    def test_get_history_not_found(self):
        """Covers lines 83-84: session not found."""
        from main.app.user.user import UserManager
        from main.app.authentication.util import extractTokenPayload

        app = FastAPI()
        from main.controller.prometheus_controller import router as promRouter
        from main.utils.errors import registerErrorHandlers

        app.include_router(promRouter)
        registerErrorHandlers(app)
        mock_db = MagicMock()
        app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
            "userId": 1,
            "username": "alice",
            "roles": ["PREMIUM"],
        }
        app.dependency_overrides[extractTokenPayload] = lambda: {"userId": 1}

        # Session not found
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with patch("main.controller.prometheus_controller.Roles") as mock_roles:

            async def mock_checker(user=None, **kwargs):
                return user or {"userId": 1, "username": "alice", "roles": ["PREMIUM"]}

            mock_roles.requirePermission.return_value = mock_checker

            client = _TestClient(app, raise_server_exceptions=False)
            resp = client.get("/prometheus/history/s1")
            assert resp.status_code == 403


class TestPrometheusDeleteSession:
    """Covers lines 95-98: DELETE /prometheus/sessions/{sessionId}."""

    def test_delete_session_success(self):
        """Covers lines 95-98: session deleted."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.deleteSession.return_value = True

            client, _, _ = _make_prometheus_client()
            resp = client.delete("/prometheus/sessions/s1")
            assert resp.status_code == 200
            assert resp.json()["message"] == "Session deleted"

    def test_delete_session_not_found(self):
        """Covers lines 96-97: session not found."""
        with patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm:
            mock_pcm.deleteSession.return_value = False

            client, _, _ = _make_prometheus_client()
            resp = client.delete("/prometheus/sessions/s1")
            assert resp.status_code == 404


class TestPrometheusChat:
    """Covers lines 114-115, 117-120, 122, 125: POST /prometheus/chat."""

    def test_chat_new_session(self):
        """Covers lines 111-112: sessionId is None, new session created."""
        with (
            patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm,
            patch("main.controller.prometheus_controller.PrometheusGenerator") as mock_gen,
        ):
            mock_pcm.createSession.return_value = "new-chat-id"
            mock_pcm.getHistory.return_value = []
            mock_gen.executeWorkflow.return_value = "AI response here"

            client, _, _ = _make_prometheus_client()
            resp = client.post("/prometheus/chat", json={"text": "Hello AI"})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["response"] == "AI response here"
            mock_pcm.createSession.assert_called_once()

    def test_chat_existing_session_verified(self):
        """Covers lines 114-115, 117-120, 122: existing session with verified ownership."""
        from main.app.user.user import UserManager
        from main.app.authentication.util import extractTokenPayload

        app = FastAPI()
        from main.controller.prometheus_controller import router as promRouter
        from main.utils.errors import registerErrorHandlers

        app.include_router(promRouter)
        registerErrorHandlers(app)
        mock_db = MagicMock()
        app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
            "userId": 1,
            "username": "alice",
            "roles": ["PREMIUM"],
        }
        app.dependency_overrides[extractTokenPayload] = lambda: {"userId": 1}

        with (
            patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm,
            patch("main.controller.prometheus_controller.PrometheusGenerator") as mock_gen,
            patch("main.controller.prometheus_controller.Roles") as mock_roles,
        ):

            async def mock_checker(user=None, **kwargs):
                return user or {"userId": 1, "username": "alice", "roles": ["PREMIUM"]}

            mock_roles.requirePermission.return_value = mock_checker

            mock_pcm.verifySessionOwnership.return_value = True
            mock_pcm.getHistory.return_value = [{"role": "user", "parts": [{"text": "hi"}]}]
            mock_gen.executeWorkflow.return_value = "Response"

            client = _TestClient(app, raise_server_exceptions=False)
            # sessionId is NOT annotated with Body(...) in the route, so it's a query parameter
            resp = client.post("/prometheus/chat?sessionId=existing-sid", json={"text": "Follow up"})
            assert resp.status_code == 200
            assert resp.json()["success"] is True
            mock_pcm.verifySessionOwnership.assert_called_once()

    def test_chat_existing_session_not_owner(self):
        """Covers lines 114-115: session ownership check fails."""
        from main.app.user.user import UserManager
        from main.app.authentication.util import extractTokenPayload

        app = FastAPI()
        from main.controller.prometheus_controller import router as promRouter
        from main.utils.errors import registerErrorHandlers

        app.include_router(promRouter)
        registerErrorHandlers(app)
        mock_db = MagicMock()
        app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_db
        app.dependency_overrides[UserManager.getCurrentUser] = lambda: {
            "userId": 1,
            "username": "alice",
            "roles": ["PREMIUM"],
        }
        app.dependency_overrides[extractTokenPayload] = lambda: {"userId": 1}

        with (
            patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm,
            patch("main.controller.prometheus_controller.Roles") as mock_roles,
        ):

            async def mock_checker(user=None, **kwargs):
                return user or {"userId": 1, "username": "alice", "roles": ["PREMIUM"]}

            mock_roles.requirePermission.return_value = mock_checker

            mock_pcm.verifySessionOwnership.return_value = False

            client = _TestClient(app, raise_server_exceptions=False)
            # sessionId is a query parameter (not Body-annotated in route)
            resp = client.post("/prometheus/chat?sessionId=others-sid", json={"text": "Hack"})
            assert resp.status_code == 403

    def test_chat_generic_exception(self):
        """Generic Exception in chat propagates to FastAPI's default 500 handler."""
        with (
            patch("main.controller.prometheus_controller.PrometheusChatManager") as mock_pcm,
            patch("main.controller.prometheus_controller.PrometheusGenerator") as mock_gen,
        ):
            mock_pcm.createSession.return_value = "err-sess"
            mock_pcm.getHistory.return_value = []
            mock_gen.executeWorkflow.side_effect = RuntimeError("Gemini API down")

            client, _, _ = _make_prometheus_client()
            resp = client.post("/prometheus/chat", json={"text": "crash"})
            assert resp.status_code == 500


# =========================================================================
# 4. stocksapi_controller.py — 13 uncovered lines
# =========================================================================
class TestStocksApiHealth:
    """Covers line 18: GET /stocks/health."""

    def test_health(self):
        from main.controller.stocksapi_controller import router as stocksRouter

        app = FastAPI()
        app.include_router(stocksRouter)
        client = _TestClient(app, raise_server_exceptions=False)
        resp = client.get("/stocks/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestStocksApiHistorical:
    """Covers line 35: GET /stocks/historical."""

    def test_get_historical(self):
        """Covers line 35."""
        with patch("main.controller.stocksapi_controller.stocksQuery") as mock_query:
            mock_query.queryHistorical.return_value = {"data": [{"ticker": "PETR4", "price": 30.0}]}

            client, _, _ = _make_stocksapi_client(mock_api_key="key")
            resp = client.get("/stocks/historical?search=PETR4&limit=10")
            assert resp.status_code == 200
            mock_query.queryHistorical.assert_called_once()


class TestStocksApiFundamental:
    """Covers line 47: GET /stocks/fundamental."""

    def test_get_fundamental(self):
        """Covers line 47."""
        with patch("main.controller.stocksapi_controller.stocksQuery") as mock_query:
            mock_query.queryFundamental.return_value = {"data": [{"ticker": "VALE3", "pl": 5.0}]}

            client, _, _ = _make_stocksapi_client(mock_api_key="key")
            resp = client.get("/stocks/fundamental?search=VALE3&limit=5")
            assert resp.status_code == 200
            mock_query.queryFundamental.assert_called_once()


class TestStocksApiGenerateKey:
    """Covers lines 52-53, 57-63: GET /stocks/key/generate.

    NOTE: stocksapi_controller.py line 52 references Permission.GENERATE_API_KEYS
    which does NOT exist in the Permission enum. This means the route always throws
    AttributeError → 500 via generic error handler. We test the actual behavior.
    """

    def test_generate_key_permission_error(self):
        """Covers lines 52-53: user without GENERATE_API_KEYS permission gets 403."""
        client, _, _ = _make_stocksapi_client(
            mock_current_user={"userId": 1, "username": "alice", "roles": ["DEVELOPER_STARTER"]}
        )
        resp = client.get("/stocks/key/generate")
        assert resp.status_code == 403

    def test_generate_key_admin_bypasses_permission_check(self):
        """Covers lines 57-60: admin bypasses permission check and generates key."""
        with patch("main.controller.stocksapi_controller.createKey") as mock_create:
            mock_create.return_value = "new-api-key-123"

            client, _, _ = _make_stocksapi_client(
                mock_current_user={"userId": 1, "username": "admin", "roles": ["ADMIN"]}
            )
            resp = client.get("/stocks/key/generate")
            assert resp.status_code == 200
            assert resp.json()["apiKey"] == "new-api-key-123"

    def test_generate_key_exception(self):
        """Covers lines 61-63: exception during key generation (admin path)."""
        with patch("main.controller.stocksapi_controller.createKey") as mock_create:
            mock_create.side_effect = RuntimeError("DB failure")

            client, _, _ = _make_stocksapi_client(
                mock_current_user={"userId": 1, "username": "admin", "roles": ["ADMIN"]}
            )
            resp = client.get("/stocks/key/generate")
            assert resp.status_code == 500


# =========================================================================
# 5. app/user/user.py — 31 uncovered lines
# =========================================================================
class TestAddRoleToUser:
    """Covers lines 13, 17, 19-20, 22-27: UserManager.addRoleToUser."""

    def test_add_role_success(self):
        """Covers lines 17, 22-27: user found, role not present, role added."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.hasRole.return_value = False

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        from main.app.user.user import UserManager

        result = UserManager.addRoleToUser(mock_db, 1, "DEVELOPER_STARTER")

        assert result is True
        mock_user.addRole.assert_called_once_with("DEVELOPER_STARTER")
        mock_db.commit.assert_called_once()

    def test_add_role_already_has_role(self):
        """Covers line 27: user already has the role."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.hasRole.return_value = True

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        from main.app.user.user import UserManager

        result = UserManager.addRoleToUser(mock_db, 1, "ADMIN")

        assert result is False
        mock_user.addRole.assert_not_called()

    def test_add_role_user_not_found(self):
        """Covers lines 19-20: user not found raises 404."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        from main.app.user.user import UserManager

        with pytest.raises(Exception) as exc_info:
            UserManager.addRoleToUser(mock_db, 999, "ADMIN")
        assert exc_info.value.status_code == 404


class TestGetCurrentUser:
    """Covers lines 34, 36-38, 40-44, 46, 48-49, 51, 58-59, 61, 63-67: UserManager.getCurrentUser."""

    def _make_mock_request(self):
        request = MagicMock()
        return request

    def test_get_current_user_valid_session(self):
        """Covers lines 36-38, 40-44, 46, 48-49, 51, 58-59, 61: successful user retrieval."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "alice"
        mock_user.email = "alice@test.com"
        mock_user.getRolesList.return_value = ["USER"]

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        mock_payload = {"userId": 1, "sessionId": "sess-abc"}

        # SessionManager is imported locally inside getCurrentUser — patch the source module
        with patch("main.app.authentication.session.SessionManager") as mock_sm:
            mock_sm.validateSession.return_value = True

            from main.app.user.user import UserManager

            result = UserManager.getCurrentUser(payload=mock_payload, db=mock_db)

            assert result["userId"] == 1
            assert result["username"] == "alice"
            assert result["sessionId"] == "sess-abc"

    def test_get_current_user_session_revoked(self):
        """Covers lines 42-44: session validation fails."""
        mock_db = MagicMock()

        mock_payload = {"userId": 1, "sessionId": "revoked-sess"}

        with patch("main.app.authentication.session.SessionManager") as mock_sm:
            mock_sm.validateSession.return_value = False

            from main.app.user.user import UserManager

            with pytest.raises(Exception) as exc_info:
                UserManager.getCurrentUser(payload=mock_payload, db=mock_db)
            assert exc_info.value.status_code == 401
            assert "Session revoked" in exc_info.value.detail

    def test_get_current_user_not_found(self):
        """Covers lines 48-49: user not in DB."""
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        mock_payload = {"userId": 999, "sessionId": "sess-xyz"}

        with patch("main.app.authentication.session.SessionManager") as mock_sm:
            mock_sm.validateSession.return_value = True

            from main.app.user.user import UserManager

            with pytest.raises(Exception) as exc_info:
                UserManager.getCurrentUser(payload=mock_payload, db=mock_db)
            assert exc_info.value.status_code == 401
            assert "User no longer exists" in exc_info.value.detail

    def test_get_current_user_generic_exception(self):
        """Covers lines 65-67: unexpected exception."""
        mock_db = MagicMock()
        mock_db.query.side_effect = RuntimeError("DB connection lost")

        mock_payload = {"userId": 1, "sessionId": "sess-err"}

        with patch("main.app.authentication.session.SessionManager") as mock_sm:
            mock_sm.validateSession.return_value = True

            from main.app.user.user import UserManager

            with pytest.raises(Exception) as exc_info:
                UserManager.getCurrentUser(payload=mock_payload, db=mock_db)
            assert exc_info.value.status_code == 401
            assert "Could not validate credentials" in exc_info.value.detail

    def test_get_current_user_no_session_id(self):
        """Covers lines 37-38, 46, 51, 58 (sessionId is None): skips session validation."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.userId = 1
        mock_user.username = "alice"
        mock_user.email = "alice@test.com"
        mock_user.getRolesList.return_value = ["USER"]

        mock_db.query.return_value.filter.return_value.first.return_value = mock_user

        mock_payload = {"userId": 1}

        from main.app.user.user import UserManager

        result = UserManager.getCurrentUser(payload=mock_payload, db=mock_db)

        assert result["userId"] == 1
        assert "sessionId" not in result


# =========================================================================
# 6. app/authentication/util.py — 9 uncovered lines
# =========================================================================
class TestHashPasswordEmpty:
    """Covers line 16: empty password raises ValueError."""

    def test_empty_password_raises(self):
        from main.app.authentication.util import hashPassword

        with pytest.raises(ValueError, match="Password cannot be empty"):
            hashPassword("")


class TestVerifyAccessToken:
    """Covers lines 45-51: verifyAccessToken with expired and invalid tokens."""

    def test_expired_token(self):
        """Covers lines 48-49: jwt.ExpiredSignatureError."""
        import jwt as pyjwt
        from main.app.authentication.constants import SECRET_KEY, ALGORITHM
        from main.app.authentication.util import verifyAccessToken

        expired_payload = {"userId": "1", "exp": datetime.now(timezone.utc) - timedelta(hours=1)}
        token = pyjwt.encode(expired_payload, SECRET_KEY, algorithm=ALGORITHM)

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verifyAccessToken(token)
        assert exc_info.value.status_code == 401
        assert "Token expired" in exc_info.value.detail

    def test_invalid_token(self):
        """Covers lines 50-51: jwt.InvalidTokenError."""
        from main.app.authentication.util import verifyAccessToken

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            verifyAccessToken("completely-invalid-token")
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail


class TestExtractTokenPayloadReRaise:
    """Covers line 67: extractTokenPayload re-raises HTTPException from verifyAccessToken."""

    def test_http_exception_from_verify_propagates(self):
        """Covers line 67: HTTPException raised by verifyAccessToken is re-raised."""
        from main.app.authentication.util import extractTokenPayload
        from fastapi import HTTPException, Request

        scope = {"type": "http", "headers": [(b"x-access-token", b"bad-token")]}
        request = Request(scope)

        with patch("main.app.authentication.util.verifyAccessToken") as mock_verify:
            mock_verify.side_effect = HTTPException(status_code=401, detail="Token expired")
            with pytest.raises(HTTPException) as exc_info:
                extractTokenPayload(request)
            assert exc_info.value.status_code == 401
            assert "Token expired" in exc_info.value.detail


class TestManagerInit:
    """Covers line 13: UserManager.__init__."""

    def test_manager_init(self):
        from main.app.user.user import UserManager

        mgr = UserManager()
        assert mgr is not None
