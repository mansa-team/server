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

    def cacheScheduler(self):
        def scheduler():
            self.getCachedStocks()
            while True:
                time.sleep(12*60*60) # 12 hours
                self.getCachedStocks()

        thread = threading.Thread(target=scheduler, daemon=True)
        thread.start()

    def getCachedStocks(self):
        try:
            with self.db.connect() as conn:
                df = pd.read_sql("SELECT * FROM b3_stocks", conn)
                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

                with self.cacheLock: 
                    self.STOCKS_CACHE = df
                
                logger.info(f"Stocks cache updated ({len(df)} records)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)

stocksCache = StocksCacheManager(stocksEngine, threading.Lock())