"""Wallet auth seam boundary: verifier goes through POST /auth/introspect."""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import Config, getSession
from main.app.authentication.introspect import introspectToken
from main.app.authentication.service_token import verifyServiceToken
from main.app.authentication.session import SessionManager
from main.app.authentication.util import createAccessToken
from main.app.wallet import auth as walletAuth
from main.controller.wallet_controller import router as walletRouter
from main.models.user import User
from main.utils.errors import registerErrorHandlers


def _fakeIntrospectPost(dbSession, monkeypatch):
    calls: list[dict] = []

    class FakeResp:
        def __init__(self, status_code, payload):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    def fakePost(url, json=None, headers=None, timeout=None):
        calls.append({"url": url, "json": json, "headers": headers})
        try:
            ok = verifyServiceToken(dbSession, (headers or {}).get("X-Service-Token", ""))
        except TypeError:
            ok = verifyServiceToken((headers or {}).get("X-Service-Token", ""))
        if not ok:
            return FakeResp(401, {"error": "Unauthorized"})
        try:
            payload = introspectToken(dbSession, (json or {}).get("token"))
        except Exception:
            return FakeResp(401, {"error": "Unauthorized"})
        return FakeResp(200, payload)

    monkeypatch.setattr(walletAuth.httpx, "post", fakePost)
    return calls


def _walletApp(dbSession):
    app = FastAPI()
    app.include_router(walletRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[getSession] = lambda: dbSession
    return app


def _seedUser(dbSession, username="seamuser"):
    user = User(username=username, email=f"{username}@example.com", passwordHash="h", roles="USER")
    dbSession.add(user)
    dbSession.commit()
    dbSession.refresh(user)
    session = SessionManager.createSession(dbSession, user.userId, "pytest")
    token = createAccessToken({"userId": str(user.userId), "sessionId": session.sessionId})
    return user, session, token


class TestWalletAuthSeam:
    def test_wallet_works_through_introspect_seam(self, dbSession, monkeypatch):
        calls = _fakeIntrospectPost(dbSession, monkeypatch)
        _, _, token = _seedUser(dbSession)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert len(calls) == 1
        assert calls[0]["url"] == f"http://{Config.USER.HOST}:{Config.USER.PORT}/auth/introspect"
        assert calls[0]["json"] == {"token": token}
        assert "X-Service-Token" in calls[0]["headers"]

    def test_missing_token_401_without_seam_call(self, dbSession, monkeypatch):
        calls = _fakeIntrospectPost(dbSession, monkeypatch)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            assert client.get("/wallet/wallets").status_code == 401
        assert calls == []

    def test_forged_token_401(self, dbSession, monkeypatch):
        _fakeIntrospectPost(dbSession, monkeypatch)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    def test_revoked_session_401(self, dbSession, monkeypatch):
        _fakeIntrospectPost(dbSession, monkeypatch)
        user, session, token = _seedUser(dbSession, username="revokedseam")
        assert SessionManager.revokeSession(dbSession, session.sessionId, user.userId)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token_401(self, dbSession, monkeypatch):
        _fakeIntrospectPost(dbSession, monkeypatch)
        user, session = _seedUser(dbSession, username="expiredseam")[:2]
        expired = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            expiresDelta=timedelta(seconds=-60),
        )
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_no_direct_get_current_user_import(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main", "controller", "wallet_controller.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "getCurrentUser" not in src
        assert "UserManager" not in src
        assert "http://" not in src

    def test_no_hardcoded_hosts_in_verifier(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main", "app", "wallet", "auth.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "localhost:3200" not in src
        assert "127.0.0.1" not in src
        assert "Config.USER.HOST" in src
        assert "Config.USER.PORT" in src
