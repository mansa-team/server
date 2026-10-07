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



