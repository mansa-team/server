"""Timed before/after probe for wallet perf fixes (swarm/wallet-fixes, lane perf-resync).

Measures with mocked network layer (no DB, no HTTP):
- (1) Target query count for PositionsManager.getPositions over N holdings.
- (2) Fallback-close wall time for K unpriced tickers at ~0.2s each.

Run: python scripts/measure_wallet_perf.py
"""

import time
from types import SimpleNamespace
from unittest.mock import patch

from main.app.wallet.market_data import MarketDataManager
from main.app.wallet.positions import PositionsManager


TICKERS = ["PETR4", "VALE3", "ITUB4", "BBDC4", "WEGE3", "RENT3"]
FALLBACK_LATENCY = 0.2


def makeDb(queryCount: dict) -> SimpleNamespace:
    holdings = [SimpleNamespace(ticker=ticker, quantity=10.0, avgPrice=20.0, rating=50.0) for ticker in TICKERS]
    targets = [SimpleNamespace(keyValue=ticker, percentIdeal=100.0 / len(TICKERS)) for ticker in TICKERS]

    class FakeQuery:
        def __init__(self, rows: list, modelName: str) -> None:
            self.rows = rows
            self.modelName = modelName

        def filter(self, *args: object) -> "FakeQuery":
            return self

        def all(self) -> list:
            if self.modelName == "Target":
                queryCount["targetQueries"] += 1
            return self.rows

        def first(self) -> object | None:
            queryCount["targetQueries"] += 1
            return None

    class FakeDb:
        def query(self, model: object) -> FakeQuery:
            name = getattr(model, "__name__", "")
            if name == "Holding":
                return FakeQuery(holdings, name)
            if name == "Target":
                return FakeQuery(targets, name)
            return FakeQuery([], name)

    return SimpleNamespace(query=FakeDb().query)


def fakeLivePrices(tickers: list[str]) -> dict[str, float | None]:
    return {ticker: None for ticker in tickers}


def fakeCloses(ticker: str) -> list:
    from datetime import date

    time.sleep(FALLBACK_LATENCY)
    return [(date(2024, 1, 1), 30.0)]


def main() -> None:
    queryCount = {"targetQueries": 0}
    with (
        patch.object(MarketDataManager, "fetchLivePrices", side_effect=fakeLivePrices),
        patch.object(MarketDataManager, "fetchPadraoCloses", side_effect=fakeCloses),
        patch("main.app.wallet.positions.WalletsManager.getWallet", return_value=None),
    ):
        start = time.perf_counter()
        result = PositionsManager.getPositions(makeDb(queryCount), 1, 1)  # type: ignore[arg-type]
        elapsedMs = (time.perf_counter() - start) * 1000.0
    print(f"holdings={len(TICKERS)} items={len(result['items'])}")
    print(f"targetQueries={queryCount['targetQueries']}")
    print(f"fallbackWallMs={elapsedMs:.0f}")
    print(f"sequentialFloorMs={len(TICKERS) * FALLBACK_LATENCY * 1000:.0f}")


if __name__ == "__main__":
    main()
