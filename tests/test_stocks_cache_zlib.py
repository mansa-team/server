import threading

import pandas as pd

from main.app.stocks_api.cache import StocksCacheManager
from main.app.stocks_api.query import StocksQueryManager


class FakeConn:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class FakeDB:
    def connect(self):
        return FakeConn()


def test_filter_cotation_column_does_not_accept_date_index():
    series = pd.Series([[{"DATA": "01-01-2024", "PRECO": 10.0}, {"DATA": "15-06-2026", "PRECO": 11.0}]])
    manager = StocksQueryManager(type("Fake", (), {"STOCKS_CACHE": None, "tickerIndex": {}, "nestedSample": None})())
    try:
        manager.filterCotationColumn(series, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"), {"0": ("01-01-2020", "01-01-2027")})
    except TypeError:
        pass
    else:
        raise AssertionError("dateIndex parameter should have been removed")


def test_filter_cotation_column_filters_by_date_without_index():
    series = pd.Series(
        [
            [{"DATA": "01-01-2024", "PRECO": 10.0}, {"DATA": "15-06-2026", "PRECO": 11.0}],
            [{"DATA": "01-01-2024", "PRECO": 20.0}, {"DATA": "10-07-2026", "PRECO": 22.0}],
        ]
    )
    manager = StocksQueryManager(type("Fake", (), {"STOCKS_CACHE": None, "tickerIndex": {}, "nestedSample": None})())
    out = manager.filterCotationColumn(series, pd.Timestamp("2026-01-01"), pd.Timestamp("2026-12-31"))
    assert out.tolist() == [
        [{"DATA": "15-06-2026", "PRECO": 11.0}],
        [{"DATA": "10-07-2026", "PRECO": 22.0}],
    ]


def test_get_cached_stocks_does_not_build_date_index(monkeypatch):
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4"],
            "NOME": ["PETROBRAS PN"],
            "COTACAO 10Y PADRAO": ['[{"DATA": "01-01-2024", "PRECO": 1.0}]'],
        }
    )
    monkeypatch.setattr(pd, "read_sql", lambda *a, **k: df)
    m = StocksCacheManager(FakeDB(), threading.Lock())
    m.getCachedStocks()
    assert not hasattr(m, "cotationDateIndex")
