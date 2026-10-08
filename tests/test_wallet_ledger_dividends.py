"""Ledger-driven dividend sync regressions (reviewer #1) + Decimal exactness (#2).

Complements tests/test_wallet_invariants.py (pure TWR properties, no DB
sync): these tests run syncEarnings through the API with a mocked market
history and assert post-liquidation accrual, pro-rata entitlement, cost
semantics end-to-end, and that programming errors propagate (#8) instead of
becoming silent fallbacks.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
import requests
from cashews import cache as cashewsCache
from freezegun import freeze_time

import main.models.wallet  # noqa: F401
from main.app.wallet.entries import EntriesManager
from tests.conftest import make_wallet_client


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _div_history(exIso="01-03-2026", payIso="01-04-2026", tipo="Dividendo", valor=2.0):
    def _get(url, params=None, headers=None, timeout=None):
        history = json.dumps(
            [
                {
                    "DATA COM": exIso,
                    "DATA PAGAMENTO": payIso,
                    "TIPO PROVENTO": tipo,
                    "VALOR AJUSTADO": valor,
                    "VALOR ORIGINAL": float("nan"),
                }
            ]
        )

        class Resp:
            status_code = 200

            @staticmethod
            def json():
                search = (params or {}).get("search", "PETR4")
                return {"data": [{"TICKER": search, "HISTORICO DIVIDENDOS": history}]}

        return Resp()

    return _get


def _seed_entry(client, side, iso, qty, price=10.0, costs=0.0):
    resp = client.post(
        "/wallet/entries",
        json={
            "side": side,
            "asset_type": "ACOES",
            "ticker": "PETR4",
            "date": iso,
            "quantity": qty,
            "price": price,
            "costs": costs,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp


@freeze_time("2026-09-30")
def test_full_sell_before_sync_still_accrues(dbSession, monkeypatch):
    """Buy -> ex-date -> full sell -> sync: dividend must accrue (#1)."""
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 100)
    _seed_entry(client, "Venda", "2026-03-20", 100, price=12.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert items == [{"ticker": "PETR4", "kind": "Div", "gross": 200.0, "net_ir_adjusted": 200.0, "status": "Recebido"}]


@freeze_time("2026-09-30")
def test_partial_sell_before_ex_is_pro_rata(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 100)
    _seed_entry(client, "Venda", "2026-02-10", 40, price=12.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 1 and items[0]["gross"] == 120.0


@freeze_time("2026-09-30")
def test_sell_after_ex_keeps_full_entitlement(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 100)
    _seed_entry(client, "Venda", "2026-03-20", 40, price=12.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 1 and items[0]["gross"] == 200.0


@freeze_time("2026-09-30")
def test_multiple_buys_before_ex_sum(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 50)
    _seed_entry(client, "Compra", "2026-02-10", 50, price=11.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 1 and items[0]["gross"] == 200.0


@freeze_time("2026-09-30")
def test_sells_around_ex_net_correctly(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 100)
    _seed_entry(client, "Venda", "2026-02-10", 30, price=12.0)
    _seed_entry(client, "Compra", "2026-02-20", 20, price=11.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 1 and items[0]["gross"] == 180.0


@freeze_time("2026-09-30")
def test_liquidated_before_pay_date_accrues_pending(dbSession, monkeypatch):
    monkeypatch.setattr(
        "main.app.wallet.positions.getSession",
        lambda: SimpleNamespace(get=_div_history(payIso="20-12-2026")),
    )
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 100)
    _seed_entry(client, "Venda", "2026-03-20", 100, price=12.0)
    items = client.get("/wallet/earnings").json()["items"]
    assert len(items) == 1
    assert items[0]["gross"] == 200.0 and items[0]["status"] == "A Receber"


@freeze_time("2026-09-30")
def test_buy_after_ex_accrues_nothing(dbSession, monkeypatch):
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-04-10", 100)
    assert client.get("/wallet/earnings").json()["items"] == []


def test_cost_basis_is_decimal_exact():
    rows = [SimpleNamespace(side="Compra", quantity=10.0, price=0.1, costs=0.0)]
    qty, avg = EntriesManager.applyEntries(Decimal(0), Decimal(0), rows)
    assert qty == Decimal("10") and str(avg) == "0.1"

    rows = [SimpleNamespace(side="Compra", quantity=3.0, price=0.1, costs=0.03)]
    qty, avg = EntriesManager.applyEntries(Decimal(0), Decimal(0), rows)
    assert qty == Decimal("3") and avg == Decimal("0.11")


def test_sell_keeps_avg_and_costs_flow_to_cashflows(dbSession, monkeypatch):
    def _live_ok(url, params=None, headers=None, timeout=None):
        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": [{"TICKER": "PETR4", "PRECO ATUAL": 30.0}]}

        return Resp()

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    # Buy cost 10x10+5 capitalized -> avg 10.5; sell proceeds 4x12-2 = 46.
    _seed_entry(client, "Compra", "2026-01-10", 10, costs=5.0)
    body = _seed_entry(client, "Venda", "2026-02-10", 4, price=12.0, costs=2.0).json()
    assert body["holding"] == {"ticker": "PETR4", "quantity": 6.0, "avgPrice": 10.5}
    rows = client.get("/wallet/cashflows?from=2026-01-01&to=2026-12-31").json()["rows"]
    assert [(row["in"], row["out"]) for row in rows] == [(105.0, 0.0), (0.0, 46.0)]


def test_programming_error_propagates_on_positions(dbSession, monkeypatch):
    def _live_ok(url, params=None, headers=None, timeout=None):
        class Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"data": [{"TICKER": "PETR4", "PRECO ATUAL": 30.0}]}

        return Resp()

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_live_ok))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 10)

    def _bug(*args, **kwargs):
        raise RuntimeError("programmer typo")

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_bug))
    assert client.get("/wallet/positions").status_code == 500


@freeze_time("2026-09-30")
def test_bug_propagates_but_timeout_falls_back_on_earnings(dbSession, monkeypatch):
    # Order matters: the bug case runs first so no autosync timestamp is
    # cached yet (a failed sync writes nothing); the timeout case then proves
    # genuine data-source failures still degrade to an empty list.
    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_div_history()))
    client, _, _ = make_wallet_client(db=dbSession)
    client.post("/wallet/wallets", json={"name": "W"})
    _seed_entry(client, "Compra", "2026-01-10", 10)

    def _bug(*args, **kwargs):
        raise RuntimeError("programmer typo")

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_bug))
    assert client.get("/wallet/earnings").status_code == 500

    def _timeout(*args, **kwargs):
        raise requests.Timeout()

    monkeypatch.setattr("main.app.wallet.positions.getSession", lambda: SimpleNamespace(get=_timeout))
    assert client.get("/wallet/earnings").json()["items"] == []
