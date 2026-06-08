import logging
import re
from collections import OrderedDict
from config import stocksEngine

import threading
import time
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

COLUMN_VALIDATOR = re.compile(r"^[A-Z0-9_ ]+$", re.IGNORECASE)
QUERY_CACHE_MAX_SIZE = 32


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.tickerIndex: dict = {}
        self.queryCache: OrderedDict = OrderedDict()
        self.QUERY_CACHE_TTL = 300  # 5 minutes TTL

    def cacheScheduler(self):
        self.getCachedStocks()
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.getCachedStocks, "interval", hours=12)
        scheduler.start()

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        cacheKey = tuple(columns) if columns else None
        now = time.time()

        if not force_refresh:
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

                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

                self.tickerIndex = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

                with self.cacheLock:
                    self.STOCKS_CACHE = df

                self.putCache(cacheKey, df, now)

                logger.info(f"Stocks cache updated ({len(df)} records, {len(self.tickerIndex)} tickers)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)

    def putCache(self, cacheKey, data, now):
        self.queryCache[cacheKey] = (data, now)
        self.queryCache.move_to_end(cacheKey)
        while len(self.queryCache) > QUERY_CACHE_MAX_SIZE:
            self.queryCache.popitem(last=False)

    def clearQueryCache(self):
        self.queryCache.clear()


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
