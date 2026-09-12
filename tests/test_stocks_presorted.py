"""P1 regression tests: pre-sorted cache invariant (TICKER asc, TIME desc).

Covers sortCacheFrame/buildTickerIndex plus the behavior contract the
query paths rely on now that per-request TIME sorts are removed:
dedup(keep="first") keeps the most-recent row per ticker, TIME display
normalization still applies, and tickerIndex points at the latest row.
Includes a timing smoke test (prints only, no timing asserts).
"""

import time
from types import SimpleNamespace

import pandas as pd
import zstandard as zstd

from main.app.stocks_api.cache import buildTickerIndex, sortCacheFrame
from main.app.stocks_api.query import StocksQueryManager


def makeFrame():
    rows = []
    for ticker in ["AAA", "ZZZ"]:
        for date, preco, pl in [
            ("2024-06-01", 30.0, 8.0),
            ("2024-01-15", 20.0, 9.0),
            ("2023-06-01", 10.0, 10.0),
        ]:
            rows.append(
                {
                    "TICKER": ticker,
                    "NOME": f"{ticker} NOME",
                    "TIME": pd.Timestamp(date),
                    "PRECO 2023": preco,
                    "PRECO 2022": preco - 1.0,
                    "P/L": pl,
                    "COTACAO 10Y PADRAO": f"cot-{ticker}-{date}",
                }
            )
    # Deliberately shuffled load order: newest rows are NOT first.
    return pd.DataFrame(rows).iloc[[5, 0, 3, 1, 4, 2]].reset_index(drop=True)


def makeManager(df):
    df = sortCacheFrame(df)
    return StocksQueryManager(SimpleNamespace(STOCKS_CACHE=df, tickerIndex=buildTickerIndex(df)))


class TestSortCacheFrame:
    def test_orders_ticker_asc_time_desc(self):
        df = sortCacheFrame(makeFrame())
        assert df["TICKER"].tolist() == ["AAA"] * 3 + ["ZZZ"] * 3
        for ticker in ["AAA", "ZZZ"]:
            times = df.loc[df["TICKER"] == ticker, "TIME"].tolist()
            assert times == sorted(times, reverse=True)

    def test_does_not_mutate_input(self):
        raw = makeFrame()
        before = raw.copy()
        sortCacheFrame(raw)
        pd.testing.assert_frame_equal(raw, before)

    def test_empty_and_missing_time_passthrough(self):
        empty = pd.DataFrame({"TICKER": []})
        assert sortCacheFrame(empty).empty
        noTime = pd.DataFrame({"TICKER": ["A"]})
        assert sortCacheFrame(noTime)["TICKER"].tolist() == ["A"]

    def test_string_time_sorts_chronologically(self):
        df = pd.DataFrame(
            {"TICKER": ["A", "A"], "TIME": ["2024-01-15", "2024-06-01"]},
        )
        out = sortCacheFrame(df)
        assert out["TIME"].tolist() == ["2024-06-01", "2024-01-15"]

    def test_index_points_at_most_recent_row(self):
        df = sortCacheFrame(makeFrame())
        index = buildTickerIndex(df)
        assert df.loc[index["AAA"], "TIME"] == pd.Timestamp("2024-06-01")
        assert df.loc[index["ZZZ"], "TIME"] == pd.Timestamp("2024-06-01")


class TestPresortedQueryBehavior:
    def test_historical_keeps_most_recent_per_ticker(self):
        qm = makeManager(makeFrame())
        res = qm.queryHistorical(fields="PRECO")
        assert res["count"] == 2
        assert [r["TICKER"] for r in res["data"]] == ["AAA", "ZZZ"]
        assert res["data"][0]["PRECO 2023"] == 30.0
        assert res["data"][0]["PRECO 2022"] == 29.0

    def test_fundamental_range_keeps_latest_and_formats_time(self):
        qm = makeManager(makeFrame())
        res = qm.queryFundamental(fields="P/L", dates="2024-01-01,2024-12-31")
        assert res["count"] == 2
        assert [r["TIME"] for r in res["data"]] == ["2024-06-01"] * 2
        assert [r["P/L"] for r in res["data"]] == [8.0, 8.0]

    def test_cotations_keeps_most_recent_per_ticker(self):
        qm = makeManager(makeFrame())
        res = qm.queryCotations(search="AAA,ZZZ")
        assert res["count"] == 2
        assert res["data"][0]["COTACAO 10Y PADRAO"] == "cot-AAA-2024-06-01"
        assert res["data"][1]["COTACAO 10Y PADRAO"] == "cot-ZZZ-2024-06-01"


class TestPresortedTimingSmoke:
    def test_before_after_shape_timing_print_only(self, capsys):
        compressor = zstd.ZstdCompressor()
        rows = []
        for i in range(120):
            ticker = f"T{i:04d}"
            for m in range(1, 31):
                payload = compressor.compress(f'{{"m": {m}}}'.encode())
                rows.append(
                    {
                        "TICKER": ticker,
                        "NOME": f"{ticker} NOME",
                        "TIME": pd.Timestamp(f"2024-{m % 12 + 1:02d}-15"),
                        "PRECO 2023": float(m),
                        "PRECO 2022": float(m - 1),
                        "COTACAO 10Y PADRAO": payload,
                    }
                )
        qm = makeManager(pd.DataFrame(rows))

        start = time.perf_counter()
        resHist = qm.queryHistorical(fields="PRECO")
        histElapsed = time.perf_counter() - start

        start = time.perf_counter()
        resCot = qm.queryCotations(search="T0001")
        cotElapsed = time.perf_counter() - start

        assert resHist["count"] == 120
        assert resCot["count"] == 1
        print(f"\n[TIMING] historical(3600 rows)->120: {histElapsed:.3f}s")
        print(f"[TIMING] cotations+zstd(30 rows): {cotElapsed:.3f}s")
        capsys.readouterr()
