import main.models.wallet  # noqa: F401
from tests.conftest import dbSession, make_wallet_client  # noqa: F401
from main.models.wallet import Wallet


def test_create_wallet_returns_201(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.post("/wallet/wallets", json={"name": "Principal"})
    assert resp.status_code == 201
    assert resp.json() == {"walletId": 1, "name": "Principal"}


def test_list_wallets_returns_only_mine(dbSession):

    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "Mine"})
    dbSession.add(Wallet(userId=2, name="Theirs"))
    dbSession.commit()
    names = [wallet["name"] for wallet in client.get("/wallet/wallets").json()]
    assert names == ["Mine"]
