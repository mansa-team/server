"""Pin the service-loopback middleware list and its ordering.

`SoloAuth.get_middleware` (authentication/mcp/provider.py) returns the loopback middleware stack.
The order is load-bearing: `ServiceLoopbackHeadersMiddleware` must run before
`AuthenticationMiddleware`, and `AuthContextMiddleware` must run inside it so the
authenticated token reaches the request context.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware, get_access_token
from starlette.middleware.authentication import AuthenticationMiddleware

from main.app.authentication.mcp import SoloAuth, SoloOAuthProvider
from main.app.authentication.service_token import createServiceToken
from main.app.authentication.util import ServiceLoopbackHeadersMiddleware


def _soloMiddleware():
    solo = SoloAuth(server=SoloOAuthProvider(), required_scopes=[])
    return solo.get_middleware()


EXPECTED_ORDER = [ServiceLoopbackHeadersMiddleware, AuthenticationMiddleware, AuthContextMiddleware]


def _classes(middlewareList):
    return [middleware.cls for middleware in middlewareList]


def _probeApp(middlewareList, dbSession, monkeypatch):
    monkeypatch.setattr("main.app.authentication.util.SessionLocal", lambda: dbSession)
    app = FastAPI(middleware=middlewareList)

    @app.get("/probe")
    async def probe():
        token = get_access_token()
        if token is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return {"client_id": token.client_id}

    return app


class TestMiddlewareOrder:
    def test_pins_exact_middleware_order(self):
        classes = _classes(_soloMiddleware())
        assert classes == EXPECTED_ORDER
        assert classes.index(ServiceLoopbackHeadersMiddleware) < classes.index(AuthenticationMiddleware)
        assert classes.index(AuthenticationMiddleware) < classes.index(AuthContextMiddleware)


class TestMiddlewareOrderIsLoadBearing:
    def test_service_token_authenticates(self, dbSession, monkeypatch):
        app = _probeApp(_soloMiddleware(), dbSession, monkeypatch)
        serviceToken = createServiceToken(dbSession)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe", headers={"X-Service-Token": serviceToken})
        assert resp.status_code == 200
        assert resp.json() == {"client_id": "service-loopback"}

    def test_missing_token_is_401(self, dbSession, monkeypatch):
        app = _probeApp(_soloMiddleware(), dbSession, monkeypatch)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe")
        assert resp.status_code == 401

    def test_reversed_order_breaks_context_propagation(self, dbSession, monkeypatch):
        app = _probeApp(list(reversed(_soloMiddleware())), dbSession, monkeypatch)
        serviceToken = createServiceToken(dbSession)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe", headers={"X-Service-Token": serviceToken})
        assert resp.status_code == 401
