import hashlib

import pytest
import requests

import main.models.wallet  # noqa: F401
import main.app.wallet.wallet_service as wallet_service
from tests.conftest import make_wallet_client
from tests.test_wallet_positions import _live_ok

RATINGS_ROUTE_DIGEST = "3a9cfe8d634aa3333c2867ef16e8c943313b5a67b6409043698521d5a2b1e686"  # sha256 of set_rating_route handler bytes (main/controller/wallet_controller.py:151-158), recorded at plan-review time


def test_buy_flag_scale_fixed_and_weights(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)  # PETR4 @ 30.0, Task 7 fake
    monkeypatch.setattr(wallet_service, "fetchXangoScores", lambda tickers: {"PETR4": 80.0})
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
    client.put(
        "/wallet/targets",
        json={"wallet_id": walletId, "key_kind": "ticker", "key_value": "PETR4", "percent_ideal": 50.0},
    )
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    assert item["percent_wallet"] == pytest.approx(1.0)
    assert item["buy_flag"] is False  # 100% held vs 50% ideal → overweight, no buy


def test_xango_none_degrades_to_p1_rule(dbSession, monkeypatch):
    monkeypatch.setattr(requests, "get", _live_ok)
    monkeypatch.setattr(wallet_service, "fetchXangoScores", lambda tickers: {"PETR4": None})
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
    client.put(
        "/wallet/targets",
        json={"wallet_id": walletId, "key_kind": "ticker", "key_value": "PETR4", "percent_ideal": 50.0},
    )
    item = client.get(f"/wallet/positions?wallet_id={walletId}").json()["items"][0]
    assert item["buy_flag"] is False  # same verdict without XANGO — degradation, not failure


def test_backtest_fewer_false_flips_than_p1():
    # Seeded checkpoint series: steady climb, 50% ideal, rating 8, XANGO 80.
    # flips = checkpoints emitting True. P1 (scale bug: fraction vs 0-100) is True
    # at all 5 checkpoints; the tuned flag clears once overweight and stays clear.
    checkpoints = [
        {"percentWallet": 0.10, "percentIdeal": 50.0, "holdingRating": 8, "xangoScore": 80.0, "appreciation": 5.0},
        {"percentWallet": 0.30, "percentIdeal": 50.0, "holdingRating": 8, "xangoScore": 80.0, "appreciation": 15.0},
        {"percentWallet": 0.60, "percentIdeal": 50.0, "holdingRating": 8, "xangoScore": 80.0, "appreciation": 40.0},
        {"percentWallet": 0.90, "percentIdeal": 50.0, "holdingRating": 8, "xangoScore": 80.0, "appreciation": 80.0},
        {"percentWallet": 1.00, "percentIdeal": 50.0, "holdingRating": 8, "xangoScore": 80.0, "appreciation": 100.0},
    ]
    p1_flags = [
        checkpoint["percentIdeal"] is not None
        and checkpoint["percentWallet"] < checkpoint["percentIdeal"]
        and (checkpoint["holdingRating"] is None or checkpoint["holdingRating"] >= 6)
        for checkpoint in checkpoints
    ]
    tuned_flags = [
        wallet_service.scoreBuyFlag(
            checkpoint["percentWallet"],
            checkpoint["percentIdeal"],
            checkpoint["holdingRating"],
            checkpoint["xangoScore"],
            checkpoint["appreciation"],
        )
        for checkpoint in checkpoints
    ]
    p1_flips = sum(1 for flag in p1_flags if flag)
    tuned_flips = sum(1 for flag in tuned_flags if flag)
    assert p1_flips == 5  # scale bug: always True
    assert tuned_flags == [True, True, False, False, False]
    assert tuned_flips < p1_flips


def test_ratings_route_untouched():
    raw = open("main/controller/wallet_controller.py", "rb").read().splitlines(keepends=True)[150:158]
    digest = hashlib.sha256(b"".join(raw)).hexdigest()
    assert digest == RATINGS_ROUTE_DIGEST  # any edit to set_rating_route fails loudly
