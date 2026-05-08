import logging
from config import stocksEngine

import threading
import time
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.ticker_index = {}
        self.query_cache = {}
        self.QUERY_CACHE_TTL = 300  # 5 minutes TTL

    def cacheScheduler(self):
        def scheduler():
            self.getCachedStocks()
            while True:
                time.sleep(12 * 60 * 60)  # 12 hours
                self.getCachedStocks()

        thread = threading.Thread(target=scheduler, daemon=True)
        thread.start()

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        cache_key = tuple(columns) if columns else None
        now = time.time()

        if not force_refresh:
            if cache_key in self.query_cache:
                cached_data, cached_time = self.query_cache[cache_key]
                if now - cached_time < self.QUERY_CACHE_TTL:
                    return cached_data

        try:
            with self.db.connect() as conn:
                if columns:
                    cols = ["TICKER", "NOME", "TIME"] + [c for c in columns if c not in ["TICKER", "NOME", "TIME"]]
                    query = f"SELECT {','.join(cols)} FROM b3_stocks"
                    df = pd.read_sql(query, conn)
                else:
                    df = pd.read_sql("SELECT * FROM b3_stocks", conn)

                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

                self.ticker_index = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

                with self.cacheLock:
                    self.STOCKS_CACHE = df

                self.query_cache[cache_key] = (df, now)

                logger.info(f"Stocks cache updated ({len(df)} records, {len(self.ticker_index)} tickers)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)

    def clearQueryCache(self):
        self.query_cache.clear()

stocksCache = StocksCacheManager(stocksEngine, threading.Lock())