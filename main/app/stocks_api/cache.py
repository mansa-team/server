import logging
import re
from collections import OrderedDict
from config import stocksEngine
import orjson

import threading
import time
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

COLUMN_VALIDATOR = re.compile(r"^[A-Z0-9_ ]+$", re.IGNORECASE)
QUERY_CACHE_MAX_SIZE = 32

CATEGORY_COLS = frozenset(["TICKER", "NOME"])


def optimizeDtypes(df: pd.DataFrame) -> pd.DataFrame:
    for col in CATEGORY_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")

    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")

    try:
        for col in df.select_dtypes(include=["object"]).columns:
            if col not in CATEGORY_COLS and df[col].notna().all():
                df[col] = df[col].astype("string[pyarrow]")
    except Exception as e:
        logger.debug(f"Arrow string optimization skipped: {e}")

    return df


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.tickerIndex: dict = {}
        self.queryCache: OrderedDict = OrderedDict()
        self.queryCacheLock = threading.Lock()
        self.QUERY_CACHE_TTL = 300  # 5 minutes TTL

    def cacheScheduler(self):
        thread = threading.Thread(target=self.getCachedStocks, name="stocks-cache-init", daemon=True)
        thread.start()
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.getCachedStocks, "interval", hours=12)
        scheduler.start()

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        cacheKey = tuple(columns) if columns else None
        now = time.time()

        if not force_refresh:
            with self.queryCacheLock:
                if cacheKey in self.queryCache:
                    cachedData, cached_time = self.queryCache[cacheKey]
                    if now - cached_time < self.QUERY_CACHE_TTL:
                        self.queryCache.move_to_end(cacheKey)
                        return cachedData
                    else:
                        del self.queryCache[cacheKey]

        try:
            with self.db.connect() as conn:
                if columns:
                    validatedCols = [c for c in columns if c and COLUMN_VALIDATOR.match(str(c))]
                    cols = ["TICKER", "NOME", "TIME"] + [
                        c for c in validatedCols if c not in ["TICKER", "NOME", "TIME"]
                    ]

                    quotedCols = [f"`{c}`" for c in cols]
                    query = f"SELECT {','.join(quotedCols)} FROM b3_stocks"
                    df = pd.read_sql(query, conn)
                else:
                    df = pd.read_sql("SELECT * FROM b3_stocks", conn)

            df = optimizeDtypes(df)

            newTickerIndex = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

            with self.cacheLock:
                self.STOCKS_CACHE = df
                self.tickerIndex = newTickerIndex

            with self.queryCacheLock:
                self.putCache(cacheKey, df, now)

            logger.info(f"Stocks cache updated ({len(df)} records, {len(newTickerIndex)} tickers)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)

    def putCache(self, cacheKey, data, now):
        self.queryCache[cacheKey] = (data, now)
        self.queryCache.move_to_end(cacheKey)
        while len(self.queryCache) > QUERY_CACHE_MAX_SIZE:
            self.queryCache.popitem(last=False)

    def clearQueryCache(self):
        with self.queryCacheLock:
            self.queryCache.clear()


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
