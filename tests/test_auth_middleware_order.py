"""Pin the service-loopback middleware list and its ordering.

`ServiceLoopbackVerifier.get_middleware` (util.py) and `SoloAuth.get_middleware`
(mcp_oauth.py) both return the loopback middleware stack. The order is
load-bearing: `ServiceLoopbackHeadersMiddleware` must run before
`AuthenticationMiddleware`, and `AuthContextMiddleware` must run inside it so the
authenticated token reaches the request context. These tests pin the order and
prove it behaviorally; without them the two lists could drift or be reordered.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from mcp.server.auth.middleware.auth_context import AuthContextMiddleware, get_access_token
from starlette.middleware.authentication import AuthenticationMiddleware

from config import Config
from main.app.authentication.mcp_oauth import SoloAuth, SoloOAuthProvider
from main.app.authentication.service_token import createServiceToken
from main.app.authentication.util import (
    JWT_ALGORITHM,
    ServiceLoopbackHeadersMiddleware,
    ServiceLoopbackVerifier,
)


def _verifierMiddleware():
    verifier = ServiceLoopbackVerifier(public_key=Config.USER.JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return verifier.get_middleware()


def _soloMiddleware():
    verifier = ServiceLoopbackVerifier(public_key=Config.USER.JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    provider = SoloOAuthProvider()
    solo = SoloAuth(server=provider, verifiers={"service-loopback": verifier}, required_scopes=[])
    return solo.get_middleware()


FACTORIES = [_verifierMiddleware, _soloMiddleware]

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
    @pytest.mark.parametrize("factory", FACTORIES)
    def test_pins_exact_middleware_order(self, factory):
        classes = _classes(factory())
        assert classes == EXPECTED_ORDER
        assert classes.index(ServiceLoopbackHeadersMiddleware) < classes.index(AuthenticationMiddleware)
        assert classes.index(AuthenticationMiddleware) < classes.index(AuthContextMiddleware)

    def test_both_providers_share_one_shape(self):
        assert _classes(_verifierMiddleware()) == _classes(_soloMiddleware()) == EXPECTED_ORDER


class TestMiddlewareOrderIsLoadBearing:
    @pytest.mark.parametrize("factory", FACTORIES)
    def test_service_token_authenticates(self, factory, dbSession, monkeypatch):
        app = _probeApp(factory(), dbSession, monkeypatch)
        serviceToken = createServiceToken(dbSession)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe", headers={"X-Service-Token": serviceToken})
        assert resp.status_code == 200
        assert resp.json() == {"client_id": "service-loopback"}

    @pytest.mark.parametrize("factory", FACTORIES)
    def test_missing_token_is_401(self, factory, dbSession, monkeypatch):
        app = _probeApp(factory(), dbSession, monkeypatch)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe")
        assert resp.status_code == 401

    def test_reversed_order_breaks_context_propagation(self, dbSession, monkeypatch):
        app = _probeApp(list(reversed(_verifierMiddleware())), dbSession, monkeypatch)
        serviceToken = createServiceToken(dbSession)
        with TestClient(app, raise_server_exceptions=False) as client:
            resp = client.get("/probe", headers={"X-Service-Token": serviceToken})
        assert resp.status_code == 401
