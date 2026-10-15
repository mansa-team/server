"""Wallet auth seam: wallet routes resolve identity in-process.

`getWalletUser` calls `introspectToken(db, raw)` directly — no service-token
mint, no self-HTTP call, no `user_sessions` row per request.
"""

import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from fastapi import FastAPI
from fastapi.testclient import TestClient

from config import getSession
from main.app.authentication import service_token as serviceTokens
from main.app.authentication.constants import COOKIE_NAME
from main.app.authentication.session import SessionManager
from main.app.authentication.util import createAccessToken
from main.app.wallet import auth as walletAuth
from main.controller.wallet_controller import router as walletRouter
from main.models.user import User
from main.models.user_session import UserSession
from main.utils.errors import registerErrorHandlers


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
    def test_wallet_works_in_process_without_service_session(self, dbSession, monkeypatch):
        def _fail(*args, **kwargs):
            raise AssertionError("createServiceToken must not be called on the wallet path")

        monkeypatch.setattr(serviceTokens, "createServiceToken", _fail)
        _, _, token = _seedUser(dbSession)
        sessionsBefore = dbSession.query(UserSession).count()

        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            client.cookies.set(COOKIE_NAME, token)
            resp = client.get("/wallet/wallets")

        assert resp.status_code == 200
        assert dbSession.query(UserSession).count() == sessionsBefore

    def test_wallet_works_with_bearer_header(self, dbSession):
        _, _, token = _seedUser(dbSession)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_missing_token_401(self, dbSession):
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            assert client.get("/wallet/wallets").status_code == 401

    def test_forged_token_401(self, dbSession):
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": "Bearer not.a.real.token"})
        assert resp.status_code == 401

    def test_revoked_session_401(self, dbSession):
        user, session, token = _seedUser(dbSession, username="revokedseam")
        assert SessionManager.revokeSession(dbSession, session.sessionId, user.userId)
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_expired_token_401(self, dbSession):
        user, session = _seedUser(dbSession, username="expiredseam")[:2]
        expired = createAccessToken(
            {"userId": str(user.userId), "sessionId": session.sessionId},
            expiresDelta=timedelta(seconds=-60),
        )
        with TestClient(_walletApp(dbSession), raise_server_exceptions=False) as client:
            resp = client.get("/wallet/wallets", headers={"Authorization": f"Bearer {expired}"})
        assert resp.status_code == 401

    def test_mint_service_token_helper_removed(self):
        assert not hasattr(walletAuth, "mintServiceToken")

    def test_wallet_auth_module_has_no_self_http(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main", "app", "wallet", "auth.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "httpx" not in src
        assert "createServiceToken" not in src
        assert "Config.USER" not in src
        assert "introspectToken" in src

    def test_no_direct_get_current_user_import(self):
        path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "main", "controller", "wallet_controller.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        assert "getCurrentUser" not in src
        assert "UserManager" not in src
        assert "http://" not in src
