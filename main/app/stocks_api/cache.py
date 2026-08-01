import logging
from config import stocksEngine
import orjson
import threading

import pandas as pd
import numpy as np

from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler

import os
import subprocess
import sys
import time
import zstandard as zstd
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

CATEGORY_COLS = frozenset(["TICKER", "NOME"])

COMPRESS_COLS = frozenset(["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"])

CACHE_FEATHER_PATH = Path("/app/cache/stocks_cache.feather")
CACHE_NESTED_PATH = Path("/app/cache/stocks_nested.feather")
STALE_AFTER_SECONDS = 6 * 3600


def optimizeDtypes(df: pd.DataFrame) -> pd.DataFrame:
    for col in CATEGORY_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")

    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")

    try:
        for col in df.select_dtypes(include=["object"]).columns:
            if col not in CATEGORY_COLS and col not in COMPRESS_COLS and df[col].notna().all():
                df[col] = df[col].astype("string[pyarrow]")
    except Exception as e:
        logger.debug(f"Arrow string optimization skipped: {e}")

    return df


def buildFeatherCache():
    # subprocess entry: heavy read+compress happens here so the peak memory dies with this process
    with stocksEngine.connect() as conn:
        df = pd.read_sql("SELECT * FROM b3_stocks", conn)
    df = optimizeDtypes(df)
    sampleCols = [c for c in COMPRESS_COLS if c in df.columns]
    nestedSample = df[sampleCols].head(5).copy() if sampleCols else None
    for col in sampleCols:
        df[col] = df[col].map(
            lambda s: zstd.ZstdCompressor(level=3).compress(s.encode("utf-8")) if isinstance(s, str) else None
        )
    CACHE_FEATHER_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_feather(CACHE_FEATHER_PATH)
    if nestedSample is not None:
        nestedSample.to_feather(CACHE_NESTED_PATH)
    print(f"feather written to {CACHE_FEATHER_PATH} ({len(df)} records)")


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.tickerIndex: dict = {}
        self.nestedSample = None
        self.lastCacheUpdate = None

    def cacheScheduler(self):
        thread = threading.Thread(target=self.getCachedStocks, name="stocks-cache-init", daemon=True)
        thread.start()
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.getCachedStocks, "interval", hours=12)
        scheduler.start()

    def loadFromFeather(self):
        df = pd.read_feather(CACHE_FEATHER_PATH)
        nestedSample = pd.read_feather(CACHE_NESTED_PATH) if CACHE_NESTED_PATH.exists() else None

        newTickerIndex = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

        with self.cacheLock:
            self.STOCKS_CACHE = df
            self.tickerIndex = newTickerIndex
            self.nestedSample = nestedSample
            self.lastCacheUpdate = datetime.now(timezone.utc)

        from main.app.stocks_api.compress import rebuildAbbrevs

        rebuildAbbrevs()

        logger.info(f"Stocks cache loaded from feather ({len(df)} records, {len(newTickerIndex)} tickers)")

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        try:
            if not CACHE_FEATHER_PATH.exists():
                subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "from main.app.stocks_api.cache import buildFeatherCache; buildFeatherCache()",
                    ],
                    check=True,
                )
            self.loadFromFeather()
        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
