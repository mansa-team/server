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
    client.post("/wallet/wallets", json={"name": "W"})
    client.post(
        "/wallet/entries",
        json={
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
    client.post("/wallet/wallets", json={"name": "W"})
    client.post(
        "/wallet/entries",
        json={
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
            "side": "Venda",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-04-10",
            "quantity": 99,
            "price": 30.0,
        },
    )
    assert bad.status_code == 422
    items = client.get("/wallet/entries").json()
    assert items["total"] == 2


def test_edit_replays_holding_from_ledger(dbSession):
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    first = client.post(
        "/wallet/entries",
        json={
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


def test_cross_user_wallet_isolated_404(dbSession):
    # No userId/wallet_id is accepted from the client anymore: user 2's wallet
    # is unreachable from user 1's identity. Collection reads show only my
    # data; entryId-scoped writes on another user's entries return 404.
    from datetime import date

    from main.models.wallet import Transaction, Wallet

    victim = Wallet(userId=2, name="Theirs")
    dbSession.add(victim)
    dbSession.flush()
    dbSession.add(
        Transaction(
            walletId=victim.walletId,
            side="Compra",
            assetType="ACOES",
            ticker="PETR4",
            date=date(2026, 1, 10),
            quantity=1,
            price=1.0,
            costs=0.0,
        )
    )
    dbSession.commit()
    victimId = dbSession.query(Transaction).first().entryId
    client, _, _ = make_wallet_client(db=dbSession)
    assert client.get("/wallet/entries").json() == {"total": 0, "items": []}
    assert client.patch(f"/wallet/entries/{victimId}", json={"quantity": 5}).status_code == 404
    assert client.delete(f"/wallet/entries/{victimId}").status_code == 404
    # My own write lands in my wallet, never in the victim's.
    mine = client.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 1,
            "price": 1.0,
        },
    )
    assert mine.status_code == 201
    assert client.get("/wallet/entries").json()["total"] == 1


def test_compra_rejects_acao_singular(dbSession):
    # Strict shape: only "ACOES"/"OUTROS" accepted; the old singular form is 422.
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    resp = client.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACAO",
            "ticker": "WEGE3",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 40.0,
        },
    )
    assert resp.status_code == 422


def test_second_user_sees_own_wallet_not_404(dbSession):
    # Session scoping: user 2 resolves to their OWN wallet (200 + own rows),
    # never user 1's data and never a 404 on collection reads.
    user1, _, _ = make_wallet_client(db=dbSession)
    user1.post("/wallet/wallets", json={"name": "W"})
    user1.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    )
    user2, _, _ = make_wallet_client(mock_identity={"userId": 2, "username": "other", "roles": ["USER"]}, db=dbSession)
    assert user2.get("/wallet/entries").json() == {"total": 0, "items": []}
    mine = user2.post(
        "/wallet/entries",
        json={
            "side": "Compra",
            "asset_type": "ACOES",
            "ticker": "VALE3",
            "date": "2026-01-10",
            "quantity": 5,
            "price": 20.0,
        },
    )
    assert mine.status_code == 201
    body = user2.get("/wallet/entries").json()
    assert body["total"] == 1
    assert [item["ticker"] for item in body["items"]] == ["VALE3"]
