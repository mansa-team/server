import pytest

import main.models.wallet  # noqa: F401
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def test_compra_average_includes_costs(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
            "costs": 0.0,
        },
    )
    resp = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-02-10",
            "quantity": 10,
            "price": 20.0,
            "costs": 5.0,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["holding"] == {"ticker": "PETR4", "quantity": 20.0, "avgPrice": 15.25}


def test_venda_keeps_avg_and_rejects_oversell(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 20,
            "price": 10.0,
        },
    )
    resp = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Venda",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-03-10",
            "quantity": 5,
            "price": 30.0,
        },
    )
    assert resp.json()["holding"] == {"ticker": "PETR4", "quantity": 15.0, "avgPrice": 10.0}
    bad = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Venda",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-04-10",
            "quantity": 99,
            "price": 30.0,
        },
    )
    assert bad.status_code == 422
    items = client.get(f"/wallet/entries?wallet_id={walletId}").json()
    assert items["total"] == 2


def test_edit_replays_holding_from_ledger(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    first = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    ).json()
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-02-10",
            "quantity": 10,
            "price": 20.0,
            "costs": 5.0,
        },
    )
    resp = client.patch(f"/wallet/entries/{first['entryId']}", json={"quantity": 20})
    assert resp.json()["holding"] == {"ticker": "PETR4", "quantity": 30.0, "avgPrice": 13.5}


def test_cross_user_wallet_returns_404(dbSession):
    from main.models.wallet import Wallet

    dbSession.add(Wallet(userId=2, name="Theirs"))
    dbSession.commit()
    client, _, _ = make_wallet_client(db=dbSession)
    resp = client.post(
        "/wallet/entries",
        json={
            "wallet_id": 1,
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 1,
            "price": 1.0,
        },
    )
    assert resp.status_code == 404


def test_compra_accepts_acao_alias(dbSession):
    # Frontend Tipo field defaults to "ACAO" (singular); backend normalizes to ACOES.
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    resp = client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "ACAO",
            "ticker": "WEGE3",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 40.0,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["holding"] == {"ticker": "WEGE3", "quantity": 10.0, "avgPrice": 40.0}
    items = client.get(f"/wallet/entries?wallet_id={walletId}").json()
    assert items["items"][0]["asset_type"] == "ACOES"
