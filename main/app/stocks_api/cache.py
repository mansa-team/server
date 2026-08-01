import logging
import zlib
from config import stocksEngine
import orjson

import threading
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)

CATEGORY_COLS = frozenset(["TICKER", "NOME"])

COMPRESS_COLS = frozenset(["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS"])


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
        self.nestedSample = None

    def cacheScheduler(self):
        thread = threading.Thread(target=self.getCachedStocks, name="stocks-cache-init", daemon=True)
        thread.start()
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.getCachedStocks, "interval", hours=12)
        scheduler.start()

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        try:
            with self.db.connect() as conn:
                df = pd.read_sql("SELECT * FROM b3_stocks", conn)

            df = optimizeDtypes(df)

            sampleCols = [c for c in COMPRESS_COLS if c in df.columns]
            if sampleCols:
                self.nestedSample = df[sampleCols].head(5).copy()
                for col in sampleCols:
                    df[col] = df[col].map(lambda s: zlib.compress(s.encode("utf-8")) if isinstance(s, str) else None)

            newTickerIndex = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

            with self.cacheLock:
                self.STOCKS_CACHE = df
                self.tickerIndex = newTickerIndex

            from main.app.stocks_api.compress import rebuildAbbrevs

            rebuildAbbrevs()

            logger.info(f"Stocks cache updated ({len(df)} records, {len(newTickerIndex)} tickers)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
