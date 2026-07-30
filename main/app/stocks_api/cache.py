import logging
from pathlib import Path
from config import stocksEngine
import orjson

import threading
import pandas as pd
import numpy as np
from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler


logger = logging.getLogger(__name__)

CATEGORY_COLS = frozenset(["TICKER", "NOME"])

PARQUET_PATH = Path(__file__).parent / "stocks_cache.parquet"


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


def buildCotationDateIndex(df: pd.DataFrame, col: str) -> dict:
    index = {}
    if col not in df.columns:
        return index
    for idx, val in df[col].items():
        if pd.isna(val) or not isinstance(val, str):
            continue
        try:
            entries = orjson.loads(val)
        except (ValueError, TypeError):
            continue
        if not isinstance(entries, list):
            continue
        dates = []
        for entry in entries:
            if isinstance(entry, dict) and "DATA" in entry:
                dates.append(entry["DATA"])
        if dates:
            index[idx] = (min(dates), max(dates))
    return index


class StocksCacheManager:
    def __init__(self, db: Engine, cacheLock: threading.Lock):
        self.db = db
        self.cacheLock = cacheLock
        self.STOCKS_CACHE = None
        self.tickerIndex: dict = {}
        self.cotationDateIndex: dict[str, dict] = {}

    def cacheScheduler(self):
        thread = threading.Thread(target=self.getCachedStocks, name="stocks-cache-init", daemon=True)
        thread.start()
        scheduler = BackgroundScheduler()
        scheduler.add_job(self.getCachedStocks, "interval", hours=12)
        scheduler.start()

    def getCachedStocks(self, columns: list[str] | None = None, force_refresh: bool = False):
        try:
            df = None

            if not force_refresh and PARQUET_PATH.exists():
                try:
                    df = pd.read_parquet(PARQUET_PATH)
                    logger.info(f"Loaded stocks cache from parquet ({len(df)} records)")
                except Exception as e:
                    logger.warning(f"Failed to load parquet cache, falling back to MySQL: {e}")
                    df = None

            if df is None:
                with self.db.connect() as conn:
                    df = pd.read_sql("SELECT * FROM b3_stocks", conn)

            df = optimizeDtypes(df)

            newCotationDateIndex = {}
            for cotationCol in ["COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA"]:
                newCotationDateIndex[cotationCol] = buildCotationDateIndex(df, cotationCol)

            if not force_refresh:
                try:
                    df.to_parquet(PARQUET_PATH, index=False)
                    logger.info(f"Saved stocks cache to parquet ({PARQUET_PATH})")
                except Exception as e:
                    logger.warning(f"Failed to save parquet cache: {e}")

            newTickerIndex = {str(ticker).upper(): idx for idx, ticker in enumerate(df["TICKER"])}

            with self.cacheLock:
                self.STOCKS_CACHE = df
                self.tickerIndex = newTickerIndex
                self.cotationDateIndex = newCotationDateIndex

            from main.app.stocks_api.compressor import rebuildAbbrevs

            rebuildAbbrevs()

            logger.info(f"Stocks cache updated ({len(df)} records, {len(newTickerIndex)} tickers)")

        except Exception as e:
            logger.error(f"Error updating stocks cache: {str(e)}", exc_info=True)


stocksCache = StocksCacheManager(stocksEngine, threading.Lock())
