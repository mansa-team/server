from config import engine
from main.utils.util import log

import threading
import time
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine

class StocksCacheManager:
    def __init__(self, db: Engine, cache_lock: threading.Lock):
        self.db = db
        self.cache_lock = cache_lock
        self.STOCKS_CACHE = None

    def cacheScheduler(self):
        def scheduler():
            self.getCachedStocks()
            while True:
                time.sleep(360*60) # 360 Minutes
                self.getCachedStocks()

        thread = threading.Thread(target=scheduler, daemon=True)
        thread.start()

    def getCachedStocks(self):
        try:
            with self.db.connect() as conn:
                df = pd.read_sql("SELECT * FROM b3_stocks", conn)
                df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

                with self.cache_lock: 
                    self.STOCKS_CACHE = df
                
                log("cache", f"Stocks cache updated ({len(df)} records)")

        except Exception as e:
            log("cache", f"Error updating stocks cache: {str(e)}")

stocksCache = StocksCacheManager(engine, threading.Lock())