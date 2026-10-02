"""Concurrent stress harness for wallet /positions + /rebalance (swarm/wallet-stress).

READ + measure only: FakeDb (no MySQL), stubbed requests.get (no HTTP).
Real code under test: PositionsManager.pricePass/getPositions/getRebalance,
MarketDataManager.fetchLivePrices/fillMissingCloses, sync_cache wallet:live key.

Layer attribution per call: dbMs (FakeDb.query + getWallet stub, 1ms/query
simulated indexed point-query) vs marketMs (stubbed requests.get sleeps:
live 30ms/ticker, closes 200ms/ticker) vs computeMs (total - db - market).
Cache modes: cold (clearEndpointCache before cell), warm (primed),
degraded-cold (live returns None for half the tickers -> closes fallback).

Run: $env:PYTHONPATH="D:\\Repositories\\server"; python scripts/stress_wallet.py
"""

import argparse
import logging
import statistics
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import requests

from main.app.stocks_api.sync_cache import clearEndpointCache
from main.app.wallet.market_data import MarketDataManager
from main.app.wallet.positions import PositionsManager

LIVE_LATENCY = 0.03
CLOSES_LATENCY = 0.2
DB_LATENCY = 0.001

state = threading.local()
marketLock = threading.Lock()
marketCounters = {"ms": 0.0, "live": 0, "closes": 0}
DEAD_TICKERS: set = set()
DEAD_TICKERS: set = set()


def recordMarket(ms: float, live: int = 0, closes: int = 0) -> None:
    with marketLock:
        marketCounters["ms"] += ms
        marketCounters["live"] += live
        marketCounters["closes"] += closes


def snapMarket() -> tuple[float, int, int]:
    with marketLock:
        return marketCounters["ms"], marketCounters["live"], marketCounters["closes"]


def makeHoldings(count: int) -> list:
    tickers = [f"T{i:02d}A4" for i in range(count)]
    return [SimpleNamespace(ticker=ticker, quantity=10.0, avgPrice=20.0, rating=50.0) for ticker in tickers]


class FakeQuery:
    def __init__(self, rows: list) -> None:
        self.rows = rows

    def filter(self, *args: object) -> "FakeQuery":
        return self

    def all(self) -> list:
        time.sleep(DB_LATENCY)
        state.dbMs += DB_LATENCY * 1000.0
        return self.rows

    def first(self) -> object | None:
        time.sleep(DB_LATENCY)
        state.dbMs += DB_LATENCY * 1000.0
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self, holdings: list) -> None:
        self.holdings = holdings
        self.targets = [
            SimpleNamespace(keyValue=str(holding.ticker), percentIdeal=100.0 / len(holdings)) for holding in holdings
        ]

    def query(self, model: object) -> FakeQuery:
        name = getattr(model, "__name__", "")
        if name == "Holding":
            return FakeQuery(self.holdings)
        if name == "Target":
            return FakeQuery(self.targets)
        return FakeQuery([])


def scriptedGet(
    url: str, params: dict | None = None, headers: dict | None = None, timeout: object = None
) -> SimpleNamespace:
    ticker = (params or {}).get("search", "UNK")
    if url.endswith("/stocks/cotations/live"):
        time.sleep(LIVE_LATENCY)
        recordMarket(LIVE_LATENCY * 1000.0, live=1)
        if ticker in DEAD_TICKERS:
            return SimpleNamespace(status_code=429, json=lambda: {"data": []})
        return SimpleNamespace(status_code=200, json=lambda: {"data": [{"PRECO ATUAL": 30.0}]})

    time.sleep(CLOSES_LATENCY)
    recordMarket(CLOSES_LATENCY * 1000.0, closes=1)

    class Resp:
        status_code = 200

        @staticmethod
        def json() -> dict:
            return {"data": [{"DATA": "01-01-2024", "PRECO": 25.0}, {"DATA": "02-01-2024", "PRECO": 27.5}]}

    return Resp()  # type: ignore[return-value]


def oneCall(endpoint: str, holdings: list) -> tuple[float, float]:
    state.dbMs = 0.0
    start = time.perf_counter()
    if endpoint == "positions":
        PositionsManager.getPositions(FakeDb(holdings), 1, 1)  # type: ignore[arg-type]
    else:
        PositionsManager.getRebalance(FakeDb(holdings), 1, 1)  # type: ignore[arg-type]
    totalMs = (time.perf_counter() - start) * 1000.0
    return totalMs, state.dbMs


def percentile(rows: list[float], pct: float) -> float:
    ordered = sorted(rows)
    return ordered[min(len(ordered) - 1, int(pct / 100.0 * len(ordered)))]


def runCell(endpoint: str, holdingCount: int, clients: int, mode: str) -> dict:
    holdings = makeHoldings(holdingCount)
    tickers = sorted(str(holding.ticker) for holding in holdings)
    global DEAD_TICKERS
    DEAD_TICKERS = set(tickers[: max(1, len(tickers) // 2)]) if mode == "degraded" else set()
    if mode == "warm":
        oneCall(endpoint, holdings)
    else:
        clearEndpointCache()
    calls = 10 if clients == 1 else clients
    beforeMs, beforeLive, beforeCloses = snapMarket()
    with ThreadPoolExecutor(max_workers=clients) as pool:
        results = list(pool.map(lambda _: oneCall(endpoint, holdings), range(calls)))
    afterMs, afterLive, afterCloses = snapMarket()
    totals = [row[0] for row in results]
    dbMean = statistics.mean(row[1] for row in results)
    marketMean = (afterMs - beforeMs) / calls
    computeMean = max(0.0, statistics.mean(totals) - dbMean - marketMean)
    return {
        "endpoint": endpoint,
        "holdings": holdingCount,
        "clients": clients,
        "mode": mode,
        "calls": calls,
        "p50": percentile(totals, 50),
        "p95": percentile(totals, 95),
        "max": max(totals),
        "dbMean": dbMean,
        "marketMean": marketMean,
        "computeMean": computeMean,
        "liveFetches": afterLive - beforeLive,
        "closesFetches": afterCloses - beforeCloses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    args = parser.parse_args()
    logging.disable(logging.WARNING)
    holdingCounts = [6] if args.quick else [6, 30]
    clientCounts = [1, 20] if args.quick else [1, 20, 50]
    modes = ["cold", "warm", "degraded"]
    cells = []
    with (
        patch.object(requests, "get", scriptedGet),
        patch("main.app.wallet.positions.WalletsManager.getWallet", return_value=None),
    ):
        for endpoint in ("positions", "rebalance"):
            for holdingCount in holdingCounts:
                for mode in modes:
                    for clients in clientCounts:
                        if mode == "degraded" and clients == 50:
                            continue
                        cells.append(runCell(endpoint, holdingCount, clients, mode))
    print("endpoint holdings clients mode calls p50ms p95ms maxms dbMean marketMean computeMean liveFetch closesFetch")
    for cell in cells:
        print(
            f"{cell['endpoint']} {cell['holdings']} {cell['clients']} {cell['mode']} {cell['calls']}"
            f" {cell['p50']:.0f} {cell['p95']:.0f} {cell['max']:.0f}"
            f" {cell['dbMean']:.1f} {cell['marketMean']:.0f} {cell['computeMean']:.1f}"
            f" {cell['liveFetches']} {cell['closesFetches']}"
        )


if __name__ == "__main__":
    main()
