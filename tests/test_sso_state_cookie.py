"""Tests for Google SSO state cookie flow.

The state parameter carries the frontend redirect URL opaquely through
Google's OAuth flow. /auth/google passes it via get_login_redirect(state=url).
/callback patches the sso_state cookie so fastapi-sso verification succeeds.

Token is delivered via HttpOnly cookie only — not in URL fragment.
"""

import pytest
import sys
import os
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient as TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def build_app():
    from main.controller.authentication_controller import router as authRouter
    from main.utils.errors import registerErrorHandlers
    from main.utils.logging_config import limiter
    from slowapi import _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded

    app = FastAPI()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.include_router(authRouter)
    registerErrorHandlers(app)
    return app


def override_session(app, mock_session):
    from config import getSession

    app.dependency_overrides[getSession] = lambda: mock_session


class TestGoogleEndpointSetsState:
    """Verify /auth/google passes redirect URL as state parameter."""

    def test_passes_redirect_url_as_state(self):
        """State should be the redirect URL directly."""
        app = build_app()
        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        from starlette.responses import RedirectResponse

        mock_sso.get_login_redirect = AsyncMock(
            return_value=RedirectResponse("https://accounts.google.com/o/oauth2/auth?state=test", status_code=303)
        )

        with patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso):
            client = TestClient(app, raise_server_exceptions=False)
            client.get(
                "/auth/google?redirect_url=http://localhost:3000/prometheus",
                follow_redirects=False,
            )

        state = mock_sso.get_login_redirect.call_args[1]["state"]
        assert state == "http://localhost:3000/prometheus", f"State should be the redirect URL, got {state!r}"

    def test_none_when_no_redirect_url(self):
        """Without redirect_url, state should be None."""
        app = build_app()
        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        from starlette.responses import RedirectResponse

        mock_sso.get_login_redirect = AsyncMock(
            return_value=RedirectResponse("https://accounts.google.com/o/oauth2/auth?state=test", status_code=303)
        )

        with patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso):
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/auth/google", follow_redirects=False)

        state = mock_sso.get_login_redirect.call_args[1]["state"]
        assert state is None, f"State should be None, got {state!r}"

    def test_no_sso_redirect_cookie_set(self):
        """The /google endpoint should NOT set sso_redirect cookie."""
        app = build_app()
        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        from starlette.responses import RedirectResponse

        mock_sso.get_login_redirect = AsyncMock(
            return_value=RedirectResponse("https://accounts.google.com/o/oauth2/auth?state=test", status_code=303)
        )

        with patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso):
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get(
                "/auth/google?redirect_url=http://localhost:3000/prometheus",
                follow_redirects=False,
            )

        cookies = response.headers.get_list("set-cookie")
        for cookie in cookies:
            assert "sso_redirect" not in cookie


class TestCallbackSuccess:
    """Verify callback redirects cleanly — token in cookie only."""

    def test_redirects_to_url_in_state(self):
        """On success, redirect to URL from state param — no token in URL."""
        app = build_app()
        mock_session = MagicMock()
        override_session(app, mock_session)

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        mock_user_info = MagicMock()
        mock_user_info.id = "google-123"
        mock_user_info.email = "test@gmail.com"
        mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)

        redirect_url = "http://localhost:3000/prometheus"

        with (
            patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso),
            patch("main.controller.authentication_controller.AuthenticationManager") as mock_auth_mgr,
            patch("main.controller.authentication_controller.SessionManager") as mock_session_mgr,
            patch("main.controller.authentication_controller.createAccessToken", return_value=("jwt-test", None)),
        ):
            mock_auth_mgr.authenticateGoogleUser.return_value = {
                "userId": 1,
                "username": "test",
                "roles": ["USER"],
            }
            mock_session = MagicMock()
            mock_session.sessionId = "sess-1"
            mock_session_mgr.createSession.return_value = mock_session

            client = TestClient(app, raise_server_exceptions=False)
            client.cookies.set("sso_state", redirect_url)
            response = client.get(
                f"/auth/callback?state={redirect_url}&code=fake-auth-code",
                follow_redirects=False,
            )

        assert response.status_code in (307, 302, 303)
        location = response.headers.get("location", "")
        assert "localhost:3000/prometheus" in location
        assert "#token=" not in location, f"Token must NOT be in URL fragment: {location}"

    def test_returns_json_when_no_redirect_in_state(self):
        """When state has no URL, return JSON with token."""
        app = build_app()
        mock_session = MagicMock()
        override_session(app, mock_session)

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        mock_user_info = MagicMock()
        mock_user_info.id = "google-456"
        mock_user_info.email = "none@gmail.com"
        mock_sso.verify_and_process = AsyncMock(return_value=mock_user_info)

        state_value = "not-a-url"

        with (
            patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso),
            patch("main.controller.authentication_controller.AuthenticationManager") as mock_auth_mgr,
            patch("main.controller.authentication_controller.SessionManager") as mock_session_mgr,
            patch("main.controller.authentication_controller.createAccessToken", return_value=("jwt-none", None)),
        ):
            mock_auth_mgr.authenticateGoogleUser.return_value = {
                "userId": 2,
                "username": "none",
                "roles": ["USER"],
            }
            mock_session = MagicMock()
            mock_session.sessionId = "sess-2"
            mock_session_mgr.createSession.return_value = mock_session

            client = TestClient(app, raise_server_exceptions=False)
            client.cookies.set("sso_state", state_value)
            response = client.get(
                f"/auth/callback?state={state_value}&code=fake-auth-code",
                follow_redirects=False,
            )

        assert response.status_code == 200
        assert "accessToken" in response.json()


class TestSSOLoginErrorHandling:
    """Verify SSOLoginError returns 401, not 500."""

    def test_stale_state_returns_401(self):
        """Stale sso_state cookie must produce 401, not 500."""
        app = build_app()
        mock_session = MagicMock()
        override_session(app, mock_session)

        mock_sso = AsyncMock()
        mock_sso.__aenter__ = AsyncMock(return_value=mock_sso)
        mock_sso.__aexit__ = AsyncMock(return_value=False)

        from fastapi_sso.sso.base import SSOLoginError

        async def fake_verify(request):
            raise SSOLoginError(401, "Invalid state")

        mock_sso.verify_and_process = fake_verify

        with patch("main.controller.authentication_controller.getGoogleSSO", return_value=mock_sso):
            client = TestClient(app, raise_server_exceptions=False)
            client.cookies.set("sso_state", "stale-url-from-prior-session")
            response = client.get(
                "/auth/callback?state=fresh-url&code=fake-code",
                follow_redirects=False,
            )

        assert response.status_code == 401
        body = response.json()
        assert "error" in body
        assert "SSO login failed" in body["error"] or "Invalid state" in body["error"]


class TestStateSurvivesUrlEncoding:
    """Verify state parameter survives URL encoding round-trip."""

    def test_url_in_state_survives_round_trip(self):
        """State with URL characters should survive round-trip through OAuth URL."""
        from urllib.parse import parse_qs, urlencode

        state = "http://localhost:3000/prometheus?foo=bar&baz=qux"
        encoded = urlencode({"state": state})
        decoded = parse_qs(encoded).get("state", [None])[0]
        assert decoded == state
