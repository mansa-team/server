from imports import *
import threading

STOCKS_CACHE = None
CACHE_LOCK = threading.Lock()

def cacheScheduler(engine):
    def scheduler():
        getCachedStocks(engine)
        while True:
            time.sleep(10*60) # 10 Minutes
            getCachedStocks(engine)

    thread = threading.Thread(target=scheduler, daemon=True)
    thread.start()

def getCachedStocks(engine):
    global STOCKS_CACHE

    try:
        with engine.connect() as conn:
            df = pd.read_sql("SELECT * FROM b3_stocks", conn)
            df = df.replace({np.nan: None, np.inf: None, -np.inf: None})

            with CACHE_LOCK: STOCKS_CACHE = df

    except Exception as e: pass