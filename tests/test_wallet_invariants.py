"""Invariant/property tests for the wallet financial engine (reviewer issue #3).

Hand-rolled properties (no hypothesis dependency): each test derives the
ledger fixtures and market series inline, calling
PerformanceManager.cachedPerformance directly with monkeypatched closes so no
DB or network is needed. EntriesManager.applyEntries covers the holdings side.
"""

import math
import random
from datetime import date, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import main.models.wallet  # noqa: F401
from main.app.wallet.entries import EntriesManager
from main.app.wallet.performance import PerformanceManager


@pytest.fixture(autouse=True)
async def clear_cashews_cache():
    from cashews import cache as cashewsCache

    cashewsCache.setup("mem://")
    await cashewsCache.clear()
    yield
    await cashewsCache.clear()


def _patch_closes(monkeypatch, closes_by_ticker):
    """closes_by_ticker: dict[ticker, list[(date, price)]]."""

    def fake(cls, ticker):
        return list(closes_by_ticker.get(ticker, []))

    monkeypatch.setattr(
        "main.app.wallet.performance.PositionsManager.fetchPadraoCloses",
        classmethod(fake),
    )


def _flat_series(start, days, price, prev_price=None):
    from datetime import timedelta

    series = []
    if prev_price is not None:
        series.append((start - timedelta(days=1), prev_price))
    for i in range(days):
        series.append((start + timedelta(days=i), price[i] if isinstance(price, list) else price))
    return series


def _entry(ticker, iso, side, qty, price, costs=0.0, entry_id=1):
    return (ticker, iso, side, float(qty), float(price), float(costs), entry_id)


def _twr(monkeypatch, entries, earnings, series, from_iso, to_iso, ticker="PETR4"):
    _patch_closes(monkeypatch, {ticker: series})
    out = PerformanceManager.cachedPerformance(
        7,
        ticker,
        from_iso,
        to_iso,
        "test",
        tuple(entries),
        tuple(earnings),
    )
    return out


def test_buy_hold_matches_market_return(monkeypatch):
    """buy -> hold: return ~= market-price return."""
    start = date(2026, 1, 1)
    series = _flat_series(start, 11, [10.0] * 10 + [11.0], prev_price=10.0)
    out = _twr(
        monkeypatch,
        [_entry("PETR4", "2026-01-02", "Compra", 10, 10.0)],
        [],
        series,
        "2026-01-01",
        "2026-01-11",
    )
    assert out["twr"] == pytest.approx(0.1)
    assert out["price_return"] == pytest.approx(0.1)
    assert out["dividends_received"] == 0.0


def test_dividend_positive_on_flat_price(monkeypatch):
    """price unchanged + dividend: return positive, price return ~0."""
    start = date(2026, 1, 1)
    series = _flat_series(start, 11, 10.0, prev_price=10.0)
    out = _twr(
        monkeypatch,
        [_entry("PETR4", "2025-12-20", "Compra", 10, 10.0)],
        [("PETR4", "2026-01-05", 1.0, 1.0)],
        series,
        "2026-01-01",
        "2026-01-11",
    )
    assert out["price_return"] == pytest.approx(0.0)
    assert out["twr"] == pytest.approx(0.01)
    assert out["twr"] > 0
    assert out["dividends_received"] == pytest.approx(1.0)


def test_contribution_does_not_appear_as_performance(monkeypatch):
    """Mid-window buy at market price leaves single-ticker TWR unchanged."""
    start = date(2026, 1, 1)
    series = _flat_series(start, 11, [10.0] * 10 + [11.0], prev_price=10.0)
    base = [_entry("PETR4", "2026-01-02", "Compra", 10, 10.0, entry_id=1)]
    with_extra = base + [_entry("PETR4", "2026-01-05", "Compra", 10, 10.0, entry_id=2)]
    out_base = _twr(monkeypatch, base, [], series, "2026-01-01", "2026-01-11")
    out_extra = _twr(monkeypatch, with_extra, [], series, "2026-01-01", "2026-01-11")
    assert out_extra["twr"] == pytest.approx(out_base["twr"])


def test_complete_liquidation_stays_recoverable(monkeypatch):
    """buy -> sell everything: history stays finite, holdings go to zero."""
    start = date(2026, 1, 1)
    series = _flat_series(start, 11, [10.0] * 10 + [11.0], prev_price=10.0)
    entries = [
        _entry("PETR4", "2026-01-02", "Compra", 10, 10.0, entry_id=1),
        _entry("PETR4", "2026-01-06", "Venda", 10, 10.0, entry_id=2),
    ]
    out = _twr(monkeypatch, entries, [], series, "2026-01-01", "2026-01-11")
    assert math.isfinite(out["twr"])
    assert math.isfinite(out["price_return"])

    rows = [SimpleNamespace(side=s, quantity=q, price=p, costs=c) for _, _, s, q, p, c, _ in entries]
    qty, _ = EntriesManager.applyEntries(0.0, 0.0, rows)
    assert qty == pytest.approx(0.0)


def test_oversell_rejected():
    rows = [
        SimpleNamespace(side="Compra", quantity=5.0, price=10.0, costs=0.0),
        SimpleNamespace(side="Venda", quantity=6.0, price=10.0, costs=0.0),
    ]
    with pytest.raises(HTTPException):
        EntriesManager.applyEntries(0.0, 0.0, rows)


def test_buy_cost_includes_costs():
    rows = [SimpleNamespace(side="Compra", quantity=10.0, price=10.0, costs=5.0)]
    qty, avg = EntriesManager.applyEntries(0.0, 0.0, rows)
    assert qty == pytest.approx(10.0)
    assert avg == pytest.approx(10.5)


def test_complex_ledger_consistency(monkeypatch):
    """Random buy/buy/sell/... ledgers: holdings consistent, TWR finite."""
    start = date(2026, 1, 1)
    for seed in range(8):
        rng = random.Random(1000 + seed)
        prices = [round(10 + i * 0.2 + rng.uniform(-0.5, 0.5), 2) for i in range(12)]
        series = [(date(2025, 12, 31), 10.0)] + [
            (date(2026, 1, 1) + timedelta(days=i), p) for i, p in enumerate(prices)
        ]
        entries, held, buys, sells = [], 0.0, 0.0, 0.0
        for i in range(1, 11):
            if held <= 0 or rng.random() < 0.6:
                qty = float(rng.randint(1, 10))
                entries.append(_entry("PETR4", f"2026-01-{i:02d}", "Compra", qty, prices[i - 1], entry_id=i))
                held += qty
                buys += qty
            else:
                qty = float(rng.randint(1, int(held)))
                entries.append(_entry("PETR4", f"2026-01-{i:02d}", "Venda", qty, prices[i - 1], entry_id=i))
                held -= qty
                sells += qty
        rows = [SimpleNamespace(side=s, quantity=q, price=p, costs=c) for _, _, s, q, p, c, _ in entries]
        qty, avg = EntriesManager.applyEntries(0.0, 0.0, rows)
        assert qty == pytest.approx(buys - sells)
        assert qty >= 0
        assert avg >= 0
        out = _twr(monkeypatch, entries, [], series, "2026-01-01", "2026-01-11")
        assert math.isfinite(out["twr"])
        assert math.isfinite(out["price_return"])
