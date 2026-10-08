import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import Config, getSession
from main.app.authentication.service_token import createServiceToken
from main.app.authentication.session import SessionManager
from main.app.authentication.util import createAccessToken
from main.controller.authentication_controller import router as authRouter
from main.models.user import User
from main.utils.errors import registerErrorHandlers


@pytest.fixture
def authClient(dbSession):
    app = FastAPI()
    app.include_router(authRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[getSession] = lambda: dbSession
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def makeUserToken(dbSession, username="intro_user"):
    user = User(username=username, email=f"{username}@example.com", passwordHash="hashed", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
    return user, session, token


def serviceHeaders(dbSession):
    return {"X-Service-Token": createServiceToken(dbSession)}


class TestAuthIntrospect:
    def test_valid_token_returns_user_payload(self, dbSession, authClient):
        user, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", json={"token": token}, headers=serviceHeaders(dbSession))
        assert resp.status_code == 200
        assert resp.json() == {"userId": user.userId, "username": user.username, "roles": ["USER"]}

    def test_bearer_prefixed_body_token(self, dbSession, authClient):
        _, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", json={"token": f"Bearer {token}"}, headers=serviceHeaders(dbSession))
        assert resp.status_code == 200

    def test_header_fallback(self, dbSession, authClient):
        _, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", headers={"X-Access-Token": token, **serviceHeaders(dbSession)})
        assert resp.status_code == 200

    def test_expired_token_401(self, dbSession, authClient):
        user, session, _ = makeUserToken(dbSession)
        token = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            expiresDelta=timedelta(seconds=-1),
        )
        assert (
            authClient.post("/auth/introspect", json={"token": token}, headers=serviceHeaders(dbSession)).status_code
            == 401
        )

    def test_invalid_token_401(self, dbSession, authClient):
        assert (
            authClient.post(
                "/auth/introspect", json={"token": "not.a.real.token"}, headers=serviceHeaders(dbSession)
            ).status_code
            == 401
        )

    def test_revoked_session_401(self, dbSession, authClient):
        user, session, token = makeUserToken(dbSession)
        SessionManager.revokeSession(dbSession, session.sessionId, user.userId)
        assert (
            authClient.post("/auth/introspect", json={"token": token}, headers=serviceHeaders(dbSession)).status_code
            == 401
        )

    def test_expired_session_401(self, dbSession, authClient):
        user = User(username="exp_user", email="exp_user@example.com", passwordHash="h", roles="USER")
        dbSession.add(user)
        dbSession.commit()
        dbSession.refresh(user)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        session = SessionManager.createSession(dbSession, user.userId, "pytest", expiresAt=past)
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
        assert (
            authClient.post("/auth/introspect", json={"token": token}, headers=serviceHeaders(dbSession)).status_code
            == 401
        )

    def test_missing_token_401(self, dbSession, authClient):
        assert authClient.post("/auth/introspect", json={}, headers=serviceHeaders(dbSession)).status_code == 401


class TestAuthIntrospectGenericDetail:
    def test_all_failure_paths_share_single_401_detail(self, dbSession, authClient):
        user, session, token = makeUserToken(dbSession, username="generic_user")
        expired = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            expiresDelta=timedelta(seconds=-1),
        )
        SessionManager.revokeSession(dbSession, session.sessionId, user.userId)
        bodies = [{}, {"token": "not.a.real.token"}, {"token": expired}, {"token": token}]
        errors = set()
        for body in bodies:
            resp = authClient.post("/auth/introspect", json=body, headers=serviceHeaders(dbSession))
            assert resp.status_code == 401
            errors.add(resp.json()["error"])
        assert errors == {"Unauthorized"}

    def test_unknown_user_returns_generic_401(self, dbSession):
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        from main.app.authentication.introspect import introspectToken

        _, _, token = makeUserToken(dbSession, username="ghost_user")
        mockDb = MagicMock()
        mockDb.query.return_value.filter.return_value.first.return_value = None
        with patch("main.app.authentication.introspect.SessionManager.validateSession", return_value=True):
            with pytest.raises(HTTPException) as exc_info:
                introspectToken(mockDb, token)
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == "Unauthorized"


class TestServiceTokenDerivation:
    def test_env_var_no_longer_authenticates(self, authClient, monkeypatch):
        monkeypatch.setenv("INTROSPECT_SERVICE_TOKEN", "test-service-token")
        resp = authClient.post(
            "/auth/introspect", json={"token": "x"}, headers={"X-Service-Token": "test-service-token"}
        )
        assert resp.status_code == 401

    def test_raw_signing_key_is_not_accepted(self, authClient):
        resp = authClient.post(
            "/auth/introspect", json={"token": "x"}, headers={"X-Service-Token": Config.USER.JWT_SECRET_KEY}
        )
        assert resp.status_code == 401


class TestServiceTokenLifecycle:
    def test_minted_token_authenticates(self, dbSession, authClient):
        _, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", json={"token": token}, headers=serviceHeaders(dbSession))
        assert resp.status_code == 200

    def test_unknown_token_401(self, dbSession, authClient):
        resp = authClient.post(
            "/auth/introspect", json={"token": "x"}, headers={"X-Service-Token": "no-such-service-token"}
        )
        assert resp.status_code == 401

    def test_user_session_is_not_a_service_token(self, dbSession):
        from main.app.authentication.service_token import verifyServiceToken

        _, session, _ = makeUserToken(dbSession, username="notservice")
        assert not verifyServiceToken(dbSession, session.sessionId)

    def test_revoked_service_token_401_without_restart(self, dbSession, authClient):
        from main.app.authentication.service_token import createServiceToken, getServiceUserId

        _, _, token = makeUserToken(dbSession)
        serviceToken = createServiceToken(dbSession)
        headers = {"X-Service-Token": serviceToken}
        assert authClient.post("/auth/introspect", json={"token": token}, headers=headers).status_code == 200
        assert SessionManager.revokeSession(dbSession, serviceToken, getServiceUserId(dbSession))
        assert authClient.post("/auth/introspect", json={"token": token}, headers=headers).status_code == 401

    def test_expired_service_token_401(self, dbSession):
        from main.app.authentication.service_token import createServiceToken, verifyServiceToken

        serviceToken = createServiceToken(dbSession, expiresDelta=timedelta(seconds=-1))
        assert not verifyServiceToken(dbSession, serviceToken)

    def test_each_mint_is_unique(self, dbSession):
        from main.app.authentication.service_token import createServiceToken

        assert createServiceToken(dbSession) != createServiceToken(dbSession)
