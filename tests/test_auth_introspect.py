import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import getSession
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


SERVICE_HEADERS = {"X-Service-Token": "test-service-token"}


@pytest.fixture(autouse=True)
def introspectServiceToken(monkeypatch):
    monkeypatch.setenv("INTROSPECT_SERVICE_TOKEN", "test-service-token")


class TestAuthIntrospect:
    def test_valid_token_returns_user_payload(self, dbSession, authClient):
        user, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", json={"token": token}, headers=SERVICE_HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"userId": user.userId, "username": user.username, "roles": ["USER"]}

    def test_bearer_prefixed_body_token(self, dbSession, authClient):
        _, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", json={"token": f"Bearer {token}"}, headers=SERVICE_HEADERS)
        assert resp.status_code == 200

    def test_header_fallback(self, dbSession, authClient):
        _, _, token = makeUserToken(dbSession)
        resp = authClient.post("/auth/introspect", headers={"X-Access-Token": token, **SERVICE_HEADERS})
        assert resp.status_code == 200

    def test_expired_token_401(self, dbSession, authClient):
        user, session, _ = makeUserToken(dbSession)
        token = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            expiresDelta=timedelta(seconds=-1),
        )
        assert authClient.post("/auth/introspect", json={"token": token}, headers=SERVICE_HEADERS).status_code == 401

    def test_invalid_token_401(self, dbSession, authClient):
        assert authClient.post("/auth/introspect", json={"token": "not.a.real.token"}, headers=SERVICE_HEADERS).status_code == 401

    def test_revoked_session_401(self, dbSession, authClient):
        user, session, token = makeUserToken(dbSession)
        SessionManager.revokeSession(dbSession, session.sessionId, user.userId)
        assert authClient.post("/auth/introspect", json={"token": token}, headers=SERVICE_HEADERS).status_code == 401

    def test_expired_session_401(self, dbSession, authClient):
        user = User(username="exp_user", email="exp_user@example.com", passwordHash="h", roles="USER")
        dbSession.add(user)
        dbSession.commit()
        dbSession.refresh(user)
        past = datetime.now(timezone.utc) - timedelta(days=1)
        session = SessionManager.createSession(dbSession, user.userId, "pytest", expiresAt=past)
        token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
        assert authClient.post("/auth/introspect", json={"token": token}, headers=SERVICE_HEADERS).status_code == 401

    def test_missing_token_401(self, authClient):
        assert authClient.post("/auth/introspect", json={}, headers=SERVICE_HEADERS).status_code == 401


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
            resp = authClient.post("/auth/introspect", json=body, headers=SERVICE_HEADERS)
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
