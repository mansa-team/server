"""H1 regression: logout must clear the session cookie with the same domain
(and path) it was set with, and must accept the cookie token as fallback.

Browsers key cookies by (name, domain, path) — a delete without matching
domain leaves `mansa_token` alive until JWT expiry.
"""

import sys
import os
from datetime import timedelta
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient as TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def make_auth_client():
    from main.controller.authentication_controller import router as authRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(authRouter)
    registerErrorHandlers(app)
    mock_session = MagicMock()
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: mock_session
    return TestClient(app, raise_server_exceptions=False), app, mock_session


def domain_of(set_cookie: str) -> str | None:
    for part in set_cookie.split(";"):
        part = part.strip()
        if part.lower().startswith("domain="):
            return part.split("=", 1)[1].lower()
    return None


class TestLogoutCookieDomain:
    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_logout_clears_cookie_with_matching_domain(self, mock_auth_mgr, mock_create_token, mock_session_mgr):
        """Set-Cookie expiry from /auth/logout carries the same domain as login."""
        client, _, _ = make_auth_client()
        mock_auth_mgr.authenticateUser.return_value = {"userId": 1, "username": "bob", "roles": ["USER"]}

        mock_session = MagicMock()
        mock_session.sessionId = "sess-123"
        mock_session_mgr.createSession.return_value = mock_session
        mock_create_token.return_value = ("jwt-token-abc", timedelta(hours=720))

        login = client.post("/auth/login", json={"username": "bob", "password": "secret123"})
        assert login.status_code == 200
        login_cookies = login.headers.get_list("set-cookie")
        assert any("mansa_token=" in c for c in login_cookies), f"login must set cookie: {login_cookies}"
        login_domain = next(domain_of(c) for c in login_cookies if "mansa_token=" in c)
        assert login_domain, f"login Set-Cookie must carry Domain: {login_cookies}"

        mock_session_mgr.revokeSession.return_value = True
        with patch(
            "main.controller.authentication_controller.verifyAccessToken",
            return_value={"userId": 1, "sessionId": "sess-123"},
        ):
            logout = client.post("/auth/logout", headers={"X-Access-Token": "jwt-token-abc"})

        assert logout.status_code == 200
        logout_cookies = logout.headers.get_list("set-cookie")
        cleared = [c for c in logout_cookies if "mansa_token=" in c]
        assert cleared, f"logout must expire the cookie: {logout_cookies}"
        # Expiry: empty value + expired/max-age=0 + matching domain
        assert any("max-age=0" in c.lower().replace(" ", "") for c in cleared), cleared
        logout_domain = next(domain_of(c) for c in cleared)
        assert logout_domain == login_domain, f"domain mismatch: login={login_domain} logout={logout_domain}"

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.verifyAccessToken")
    def test_logout_accepts_cookie_token_fallback(self, mock_verify, mock_session_mgr):
        """No header but a valid cookie still revokes the session server-side."""
        client, _, _ = make_auth_client()
        mock_verify.return_value = {"userId": 7, "sessionId": "sess-777"}
        mock_session_mgr.revokeSession.return_value = True

        response = client.post("/auth/logout", cookies={"mansa_token": "cookie-jwt"})
        assert response.status_code == 200
        assert response.json()["message"] == "Successfully logged out"
        mock_verify.assert_called_once_with("cookie-jwt")
        mock_session_mgr.revokeSession.assert_called_once()

    def test_resolve_cookie_domain_dev_and_prod(self):
        from main.controller.authentication_controller import resolveCookieDomain

        localhost_req = MagicMock()
        localhost_req.url.hostname = "localhost"
        assert resolveCookieDomain(localhost_req) == "localhost"

        loopback_req = MagicMock()
        loopback_req.url.hostname = "127.0.0.1"
        assert resolveCookieDomain(loopback_req) == "localhost"

        prod_req = MagicMock()
        prod_req.url.hostname = "app.example.com"
        assert resolveCookieDomain(prod_req) == "app.example.com"
