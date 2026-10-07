import json
from types import SimpleNamespace

import pytest
from freezegun import freeze_time

import main.models.wallet  # noqa: F401
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _div_fundamental(url, params=None, headers=None, timeout=None):
    # Mirrors the live /stocks/fundamental shape: data rows keyed by TICKER
    # with HISTORICO DIVIDENDOS as a JSON *string* (bare NaN tokens included,
    # as served in production). fetchMarketDividends must parse this.
    history = json.dumps(
        [
            {
                "DATA COM": "01-03-2026",
                "DATA PAGAMENTO": "01-04-2026",
                "TIPO PROVENTO": "Dividendo",
                "VALOR AJUSTADO": 2.0,
                "VALOR ORIGINAL": float("nan"),
            },
            {
                "DATA COM": "01-06-2026",
                "DATA PAGAMENTO": "20-12-2026",
                "TIPO PROVENTO": "JCP",
                "VALOR AJUSTADO": 1.0,
                "VALOR ORIGINAL": float("nan"),
            },
            {
                # Second installment, same ex-date/kind, different pay date:
                # must aggregate into ONE earning (uq_earnings_accrual), not 500.
                "DATA COM": "01-06-2026",
                "DATA PAGAMENTO": "20-11-2026",
                "TIPO PROVENTO": "JCP",
                "VALOR AJUSTADO": 0.5,
                "VALOR ORIGINAL": float("nan"),
            },
            {
                "DATA COM": "01-07-2026",
                "DATA PAGAMENTO": "20-12-2026",
                "TIPO PROVENTO": "Bonificacao",
                "VALOR AJUSTADO": 5.0,
                "VALOR ORIGINAL": float("nan"),
            },
        ]
    )

    class Resp:
        status_code = 200

        @staticmethod
        def json():
            search = (params or {}).get("search", "PETR4")
            return {
                "data": [
                    {
                        "TICKER": search,
                        "NOME": "PETROLEO BRASILEIRO",
                        "TIME": "2026-10-02",
                        "HISTORICO DIVIDENDOS": history,
                    }
                ]
            }

    return Resp()


@freeze_time("2026-09-30")
def test_sync_accrues_with_qty_at_ex_date(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_fundamental))
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
        },
    )
    # GET auto-syncs on read: first read accrues, Bonificacao skipped (not stored).
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 2
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
        "gross": 15.0,
        "net_ir_adjusted": 12.75,
        "status": "A Receber",
    }


@freeze_time("2026-09-30")
def test_sync_repeated_ex_date_kind_aggregates_without_500(dbSession, monkeypatch):
    # Same (exDate, kind) twice with different pay dates = installments of one
    # payout: sync must store ONE aggregated earning, not raise IntegrityError.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_fundamental))
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
        },
    )
    first = client.get("/wallet/earnings")
    assert first.status_code == 200
    assert len(first.json()["items"]) == 2
    again = client.get("/wallet/earnings")
    assert again.status_code == 200
    assert len(again.json()["items"]) == 2


@freeze_time("2026-09-30")
def test_sync_is_idempotent(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_fundamental))
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
        },
    )
    first = client.get("/wallet/earnings").json()["items"]
    again = client.get("/wallet/earnings").json()["items"]
    assert len(first) == 2
    assert again == first
