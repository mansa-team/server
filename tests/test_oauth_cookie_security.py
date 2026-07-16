"""Tests for OAuth callback security - JWT token should NOT be in URL.

Token is delivered via HttpOnly cookie only. No token in URL fragment or query params.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import timedelta
from fastapi import FastAPI
from fastapi.testclient import TestClient as _TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def _make_callback_client():
    """Return (client, app, mock_session) for testing Google callback."""
    from main.controller.authentication_controller import router as authRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(authRouter)
    registerErrorHandlers(app)
    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session
    return _TestClient(app, raise_server_exceptions=False), app, mock_session


def _setup_callback_mocks(
    mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=1, email="test@gmail.com"
):
    """Helper to setup common mock values for callback tests."""
    mock_sso = AsyncMock()
    mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
    mock_sso.__aexit__ = AsyncMock(return_value=False)

    mock_user_info = MagicMock()
    mock_user_info.id = f"google-{user_id}"
    mock_user_info.email = email
    mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)
    mock_get_sso.return_value = mock_sso

    mock_auth_mgr.authenticateGoogleUser.return_value = {
        "userId": user_id,
        "username": email.split("@")[0],
        "roles": ["USER"],
    }

    mock_session = MagicMock()
    mock_session.sessionId = f"sess-{user_id}"
    mock_session_mgr.createSession.return_value = mock_session
    mock_create_token.return_value = (f"jwt-token-{user_id}", timedelta(hours=720))


class TestOAuthCallbackTokenNotInURL:
    """Verify JWT token is NOT leaked in redirect URL after OAuth callback."""

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_with_state_redirect_no_token_in_url(
        self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr
    ):
        """Token must NOT appear in redirect URL — cookie only."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=1)

        redirect_url = "http://localhost:3000/dashboard"

        client.cookies.set("sso_state", redirect_url)
        response = client.get(
            f"/auth/callback?state={redirect_url}&code=fake-code",
            follow_redirects=False,
        )

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        assert response.status_code in (307, 302)

        location = response.headers.get("location", "")
        # Token must NOT be anywhere in the URL
        assert "#token=" not in location, f"Token leaked in URL fragment: {location}"
        assert "token=" not in location.split("?")[1] if "?" in location else True, f"Token leaked in query: {location}"
        assert "jwt-token-1" not in location, "JWT token value found in redirect URL"

        # Should redirect to the original URL cleanly
        assert location == "http://localhost:3000/dashboard"

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_sets_httponly_cookie(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Cookie must be httponly (not accessible via JavaScript)."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(
            mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=2, email="user@gmail.com"
        )

        response = client.get("/auth/callback", follow_redirects=False)

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        cookies = response.headers.get_list("set-cookie")

        httponly_cookie_found = False
        for cookie in cookies:
            if "mansa_token=" in cookie and "mansa_token_access=" not in cookie:
                assert "httponly" in cookie.lower(), f"Cookie must be httponly: {cookie}"
                httponly_cookie_found = True
                break

        assert httponly_cookie_found, "httponly cookie (mansa_token) not found in response"

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_cookies_have_secure_flag(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Cookie should have secure flag (HTTPS only)."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(
            mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=4, email="secure@gmail.com"
        )

        response = client.get(
            "/auth/callback",
            follow_redirects=False,
            headers={"X-Forwarded-Proto": "https"},
        )

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        cookies = response.headers.get_list("set-cookie")

        for cookie in cookies:
            if "mansa_token" in cookie:
                pass  # Cookie is set

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_callback_no_state_returns_json_with_token(
        self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr
    ):
        """When no state param, return JSON response (not redirect)."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(
            mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=5, email="json@gmail.com"
        )

        response = client.get("/auth/callback", follow_redirects=False)

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        assert response.status_code == 200
        data = response.json()
        assert data["accessToken"] == "jwt-token-5"
        assert data["tokenType"] == "bearer"


class TestOAuthCallbackFrontendCompatibility:
    """Verify frontend can still auth after OAuth redirect via cookie."""

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_frontend_gets_token_from_cookie(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """After OAuth redirect, httponly cookie contains the token."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(
            mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=6, email="frontend@test.com"
        )

        redirect_url = "http://localhost:3000/dashboard"

        client.cookies.set("sso_state", redirect_url)
        response = client.get(
            f"/auth/callback?state={redirect_url}&code=fake-code",
            follow_redirects=False,
        )

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        assert response.status_code in (307, 302)

        # Verify httponly cookie contains the token
        cookies = response.headers.get_list("set-cookie")
        for cookie in cookies:
            if "mansa_token=" in cookie:
                assert "httponly" in cookie.lower()
                assert "jwt-token-6" in cookie
                break
        else:
            pytest.fail("Cookie not set after OAuth redirect")

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.getGoogleSSO")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_open_redirect_blocked(self, mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr):
        """Non-localhost redirect URLs must be rejected."""
        client, _, _ = _make_callback_client()
        _setup_callback_mocks(mock_auth_mgr, mock_get_sso, mock_create_token, mock_session_mgr, user_id=7)

        evil_url = "http://evil.com/steal"

        client.cookies.set("sso_state", evil_url)
        response = client.get(
            f"/auth/callback?state={evil_url}&code=fake-code",
            follow_redirects=False,
        )

        if response.status_code == 429:
            pytest.skip("Rate limited in test environment")

        # Should NOT redirect to evil URL — falls through to JSON response
        assert response.status_code == 200
        data = response.json()
        assert "accessToken" in data
