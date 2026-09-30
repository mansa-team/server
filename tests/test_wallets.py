import main.models.wallet  # noqa: F401
from tests.conftest import dbSession, make_wallet_client  # noqa: F401


def test_create_wallet_returns_201(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.post("/wallet/wallets", json={"name": "Principal"})
    assert resp.status_code == 201
    assert resp.json() == {"walletId": 1, "name": "Principal"}


def test_list_wallets_returns_only_mine(dbSession):
    from main.models.wallet import Wallet

    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "Mine"})
    dbSession.add(Wallet(userId=2, name="Theirs"))
    dbSession.commit()
    names = [wallet["name"] for wallet in client.get("/wallet/wallets").json()]
    assert names == ["Mine"]


def test_no_token_returns_401():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import MagicMock

    from main.controller.wallet_controller import router as walletRouter
    from main.utils.errors import registerErrorHandlers

    app = FastAPI()
    app.include_router(walletRouter)
    registerErrorHandlers(app)
    app.dependency_overrides[__import__("config", fromlist=["getSession"]).getSession] = lambda: MagicMock()
    resp = TestClient(app, raise_server_exceptions=False).get("/wallet/wallets")
    assert resp.status_code == 401
