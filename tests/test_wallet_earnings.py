import requests
from freezegun import freeze_time

import main.models.wallet  # noqa: F401
from tests.conftest import make_wallet_client


def _div_fundamental(url, params=None, headers=None, timeout=None):
    class Resp:
        status_code = 200

        @staticmethod
        def json():
            return {
                "data": [
                    {
                        "DATA COM": "01-03-2026",
                        "DATA PAGAMENTO": "01-04-2026",
                        "TIPO PROVENTO": "Dividendo",
                        "VALOR AJUSTADO": 2.0,
                    },
                    {
                        "DATA COM": "01-06-2026",
                        "DATA PAGAMENTO": "20-12-2026",
                        "TIPO PROVENTO": "JCP",
                        "VALOR AJUSTADO": 1.0,
                    },
                    {
                        "DATA COM": "01-07-2026",
                        "DATA PAGAMENTO": "20-12-2026",
                        "TIPO PROVENTO": "Bonificacao",
                        "VALOR AJUSTADO": 5.0,
                    },
                ]
            }

    return Resp()


@freeze_time("2026-09-30")
def test_sync_accrues_with_qty_at_ex_date(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _div_fundamental)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "Stock",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    )
    body = client.post("/wallet/earnings/sync", json={"wallet_id": walletId}).json()
    assert body == {"accrued": 2, "transitioned": 0, "skipped_unknown": ["Bonificacao"]}
    items = client.get(f"/wallet/earnings?wallet_id={walletId}").json()["items"]
    by_kind = {r["kind"]: r for r in items}
    assert by_kind["Div"] == {
        "ticker": "PETR4",
        "kind": "Div",
        "gross": 20.0,
        "net_ir_adjusted": 20.0,
        "status": "Recebido",
    }
    assert by_kind["JSCP"] == {
        "ticker": "PETR4",
        "kind": "JSCP",
        "gross": 10.0,
        "net_ir_adjusted": 8.5,
        "status": "A Receber",
    }


@freeze_time("2026-09-30")
def test_sync_is_idempotent(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _div_fundamental)
    client, _, _ = make_wallet_client(db=dbSession)
    walletId = client.post("/wallet/wallets", json={"name": "W"}).json()["walletId"]
    client.post(
        "/wallet/entries",
        json={
            "wallet_id": walletId,
            "side": "Compra",
            "asset_type": "Stock",
            "ticker": "PETR4",
            "date": "2026-01-10",
            "quantity": 10,
            "price": 10.0,
        },
    )
    client.post("/wallet/earnings/sync", json={"wallet_id": walletId})
    again = client.post("/wallet/earnings/sync", json={"wallet_id": walletId}).json()
    assert again == {"accrued": 0, "transitioned": 0, "skipped_unknown": ["Bonificacao"]}
