import logging
import os
import subprocess  # nosec: B404 used only with constant args, see getCachedStocks
import sys
import threading
import time
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy.engine import Engine

from config import stocksEngine
from main.app.stocks_api import compress, sync_cache
from main.app.stocks_api.build import (
    CACHE_FEATHER_PATH,
    CACHE_NESTED_PATH,
    buildFeatherCache,
    readFeatherDataFrame,
    tryBuildLock,
)
from main.app.stocks_api.frame import (
    CATEGORY_COLS,
    PRESORTED_FLAG_KEY,
    arrowTypeFor,
    buildTickerIndex,
    optimizeDtypes,
    sortCacheFrame,
)
from main.utils.scheduler import registerJob

__all__ = [
    "CACHE_FEATHER_PATH",
    "CACHE_LOAD_LOCK",
    "CACHE_NESTED_PATH",
    "CATEGORY_COLS",
    "PRESORTED_FLAG_KEY",
    "STALE_AFTER_SECONDS",
    "StocksCacheManager",
    "arrowTypeFor",
    "buildFeatherCache",
    "buildTickerIndex",
    "optimizeDtypes",
    "readFeatherDataFrame",
    "sortCacheFrame",
    "stocksCache",
    "tryBuildLock",
]

logger = logging.getLogger(__name__)

STALE_AFTER_SECONDS = 6 * 3600
CACHE_REFRESH_HOURS = 12
CACHE_LOAD_LOCK = threading.Lock()


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.tickerIndex: dict = {}
        self.nestedSample = None
        self.lastCacheUpdate = None

    def snapshot(self) -> tuple:
        with self.cacheLock:
            return self.STOCKS_CACHE, self.tickerIndex

    def cacheScheduler(self):
        thread = threading.Thread(target=self.getCachedStocks, name="stocks-cache-init", daemon=True)
        thread.start()
        registerJob(
            self.getCachedStocks,
            "interval",
            jobId="stocks_cache_refresh",
            jobName="Stocks cache refresh",
            hours=CACHE_REFRESH_HOURS,
        )

    def loadFromFeather(self):
        df, presorted = readFeatherDataFrame(CACHE_FEATHER_PATH)
        nestedSample = pd.read_feather(CACHE_NESTED_PATH) if CACHE_NESTED_PATH.exists() else None

        if not presorted:
            df = sortCacheFrame(df)
        newTickerIndex = buildTickerIndex(df)

        with self.cacheLock:
            self.STOCKS_CACHE = df
            self.tickerIndex = newTickerIndex
            self.nestedSample = nestedSample
            self.lastCacheUpdate = datetime.now(timezone.utc)

        compress.rebuildAbbrevs()
        sync_cache.clearEndpointCache()

        logger.info(f"Stocks cache loaded from feather ({len(df)} records, {len(newTickerIndex)} tickers)")

    def getCachedStocks(self, force_refresh: bool = False):
        try:
            if CACHE_FEATHER_PATH.exists() and not force_refresh:
                self.loadFromFeather()

                ageSeconds = time.time() - os.path.getmtime(CACHE_FEATHER_PATH)
                if ageSeconds > STALE_AFTER_SECONDS:
                    logger.info(f"Feather is {int(ageSeconds // 3600)}h old, refreshing in background")
                    threading.Thread(
                        target=self.getCachedStocks,
                        kwargs={"force_refresh": True},
                        name="stocks-cache-refresh",
                        daemon=True,
                    ).start()
                return

            if CACHE_LOAD_LOCK.acquire(blocking=False):
                try:
                    lockFile = tryBuildLock()
                    if lockFile is None:
                        logger.info("Cache build already in progress in another process, skipping")
                        return
                    try:
                        subprocess.run(
                            [
                                sys.executable,
                                "-c",
                                "from main.app.stocks_api.cache import buildFeatherCache; buildFeatherCache()",
                            ],
                            check=True,
                        )  # nosec: B603 constant args, no untrusted input
                    finally:
                        lockFile.close()
                finally:
                    CACHE_LOAD_LOCK.release()
                self.loadFromFeather()
            else:
                logger.info("Cache load already in progress, skipping")
        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
