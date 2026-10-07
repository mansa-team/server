"""CSRF route-level exemption: marker, no-cookie auto-skip, token enforcement."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.authentication.constants import COOKIE_NAME
from main.app.authentication.csrf import (
    CSRF_COOKIE_NAME,
    csrf_exempt,
    isCsrfExemptEndpoint,
    validateCsrf,
)


def makeRequest(method="POST", sessionCookie=None, csrfCookie=None, csrfHeader=None, endpoint=None):
    parts = []
    if sessionCookie is not None:
        parts.append(f"{COOKIE_NAME}={sessionCookie}")
    if csrfCookie is not None:
        parts.append(f"{CSRF_COOKIE_NAME}={csrfCookie}")
    headers = []
    if parts:
        headers.append((b"cookie", "; ".join(parts).encode()))
    if csrfHeader is not None:
        headers.append((b"x-csrf-token", csrfHeader.encode()))
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/auth/login",
        "query_string": b"",
        "headers": headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    if endpoint is not None:
        scope["route"] = SimpleNamespace(endpoint=endpoint)
    return Request(scope)


def markedEndpoint():
    async def endpoint(request):
        return {}

    return csrf_exempt(endpoint)


def plainEndpoint():
    async def endpoint(request):
        return {}

    return endpoint


class TestMarkerExemption:
    def test_marked_endpoint_skips_with_cookie_and_no_token(self):
        req = makeRequest(sessionCookie="sess-1", endpoint=markedEndpoint())
        assert isCsrfExemptEndpoint(req) is True
        validateCsrf(req, COOKIE_NAME)  # must not raise

    def test_unmarked_endpoint_is_not_exempt(self):
        req = makeRequest(sessionCookie="sess-1", endpoint=plainEndpoint())
        assert isCsrfExemptEndpoint(req) is False

    def test_routeless_scope_is_not_exempt(self):
        req = makeRequest(sessionCookie="sess-1")
        assert isCsrfExemptEndpoint(req) is False

    def test_decorator_returns_same_object(self):
        async def endpoint(request):
            return {}

        assert csrf_exempt(endpoint) is endpoint
        assert endpoint._csrf_exempt is True


class TestNoCookieAutoSkip:
    def test_post_without_session_cookie_skips(self):
        validateCsrf(makeRequest(), COOKIE_NAME)  # must not raise

    def test_post_with_only_csrf_cookie_skips(self):
        validateCsrf(makeRequest(csrfCookie="tok"), COOKIE_NAME)


class TestTokenEnforcement:
    def test_cookie_session_mutation_without_token_403(self):
        with pytest.raises(HTTPException) as exc:
            validateCsrf(makeRequest(sessionCookie="sess-1"), COOKIE_NAME)
        assert exc.value.status_code == 403

    def test_mismatched_token_403(self):
        req = makeRequest(sessionCookie="sess-1", csrfCookie="aaa", csrfHeader="bbb")
        with pytest.raises(HTTPException) as exc:
            validateCsrf(req, COOKIE_NAME)
        assert exc.value.status_code == 403

    def test_matching_token_passes(self):
        req = makeRequest(sessionCookie="sess-1", csrfCookie="tok-1", csrfHeader="tok-1")
        validateCsrf(req, COOKIE_NAME)  # must not raise

    def test_safe_method_skips_despite_cookie(self):
        validateCsrf(makeRequest(method="GET", sessionCookie="sess-1"), COOKIE_NAME)


class TestControllerMarkers:
    @staticmethod
    def endpoints():
        from main.controller.authentication_controller import router

        return {route.path: route.endpoint for route in router.routes if hasattr(route, "path")}

    def test_entry_points_marked(self):
        endpoints = self.endpoints()
        for path in ("/auth/login", "/auth/register", "/auth/google", "/auth/callback"):
            assert getattr(endpoints[path], "_csrf_exempt", False) is True, path

    def test_ambient_auth_routes_not_marked(self):
        endpoints = self.endpoints()
        for path in ("/auth/logout", "/auth/introspect", "/auth/health"):
            assert getattr(endpoints[path], "_csrf_exempt", False) is False, path

    def test_csrf_route_deleted(self):
        endpoints = self.endpoints()
        assert "/auth/csrf" not in endpoints


class TestCsrfAutoIssuance:
    """No issuer endpoint: login/register/OAuth Set-Cookie carries mansa_csrf."""

    @staticmethod
    def makeClient():
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from main.controller.authentication_controller import router as authRouter
        from main.utils.errors import registerErrorHandlers

        app = FastAPI()
        app.include_router(authRouter)
        registerErrorHandlers(app)
        return TestClient(app, raise_server_exceptions=False)

    @staticmethod
    def csrfValue(setCookies):
        return next(c.split(";")[0].split("=", 1)[1] for c in setCookies if c.startswith(f"{CSRF_COOKIE_NAME}="))

    def test_csrf_path_returns_404(self):
        assert self.makeClient().get("/auth/csrf").status_code == 404

    @patch("main.controller.authentication_controller.SessionManager")
    @patch("main.controller.authentication_controller.createAccessToken")
    @patch("main.controller.authentication_controller.AuthenticationManager")
    def test_login_sets_csrf_cookie_and_rotates(self, mock_auth_mgr, mock_create_token, mock_session_mgr):
        from unittest.mock import MagicMock

        client = self.makeClient()
        mock_auth_mgr.authenticateUser.return_value = {"userId": 1, "username": "bob", "roles": ["USER"]}
        mock_create_token.return_value = "jwt-token-abc"

        tokens = []
        for sessionId in ("sess-1", "sess-2"):
            mock_session = MagicMock()
            mock_session.sessionId = sessionId
            mock_session_mgr.createSession.return_value = mock_session
            login = client.post("/auth/login", json={"username": "bob", "password": "secret123"})
            assert login.status_code == 200
            cookies = login.headers.get_list("set-cookie")
            assert any(c.startswith(f"{CSRF_COOKIE_NAME}=") for c in cookies), cookies
            tokens.append(self.csrfValue(cookies))
        assert tokens[0] and tokens[0] != tokens[1]
