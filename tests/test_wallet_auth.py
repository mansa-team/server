from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import main.app.wallet.auth as walletAuth
from main.app.wallet.auth import requireWalletUser


def make_probe_app(monkeypatch, raw="tok123", roles=None):
    seen = {}

    def fake_introspect(db, token):
        seen["raw"] = token
        return {"userId": 1, "username": "u", "roles": roles if roles is not None else ["USER"]}

    monkeypatch.setattr(walletAuth, "introspectToken", fake_introspect)
    app = FastAPI()

    @app.get("/probe")
    def probe(user: dict = Depends(requireWalletUser)):
        return user

    return TestClient(app, raise_server_exceptions=False), seen


def test_bearer_header_reaches_introspect_without_prefix(monkeypatch):
    client, seen = make_probe_app(monkeypatch)
    resp = client.get("/probe", headers={"Authorization": "Bearer tok123"})
    assert resp.status_code == 200
    assert seen["raw"] == "tok123"


def test_access_token_header_wins(monkeypatch):
    client, seen = make_probe_app(monkeypatch)
    resp = client.get("/probe", headers={"X-Access-Token": "tokABC"})
    assert resp.status_code == 200
    assert seen["raw"] == "tokABC"


def test_cookie_fallback_pinned_to_mansa_token(monkeypatch):
    client, seen = make_probe_app(monkeypatch)
    resp = client.get("/probe", cookies={"mansa_token": "tokCK"})
    assert resp.status_code == 200
    assert seen["raw"] == "tokCK"


def test_no_token_returns_401(monkeypatch):
    client, _ = make_probe_app(monkeypatch)
    assert client.get("/probe").status_code == 401


def test_role_without_wallet_returns_403(monkeypatch):
    client, _ = make_probe_app(monkeypatch, roles=[])
    resp = client.get("/probe", headers={"Authorization": "Bearer tok123"})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Missing required permission: WALLET"
