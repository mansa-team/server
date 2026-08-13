import logging
from config import stocksEngine
from main.app.stocks_api.util import JSON_COLUMNS
import orjson
import threading

import pandas as pd
import numpy as np
import pyarrow as pa

from sqlalchemy.engine import Engine
from apscheduler.schedulers.background import BackgroundScheduler

import os
import subprocess
import sys
import time
import zstandard as zstd
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import sys

fcntl: Any = None
if sys.platform != "win32":
    import fcntl

logger = logging.getLogger(__name__)

CATEGORY_COLS = frozenset(["TICKER", "NOME"])

CACHE_FEATHER_PATH = Path("/app/cache/stocks_cache.feather")
CACHE_NESTED_PATH = Path("/app/cache/stocks_nested.feather")
STALE_AFTER_SECONDS = 6 * 3600
CACHE_LOAD_LOCK = threading.Lock()


def optimizeDtypes(df: pd.DataFrame) -> pd.DataFrame:
    for col in CATEGORY_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")

    for col in df.select_dtypes(include=["float64"]).columns:
        df[col] = pd.to_numeric(df[col], downcast="float")

    try:
        for col in df.columns:
            if str(df[col].dtype) not in ("object", "str"):
                continue
            if col not in CATEGORY_COLS and col not in JSON_COLUMNS and df[col].notna().all():
                df[col] = df[col].astype("string[pyarrow]")
    except Exception as e:
        logger.debug(f"Arrow string optimization skipped: {e}")

    return df


def arrowTypeFor(dbType: str):
    base = dbType.split()[0]
    if base in ("float", "double", "decimal"):
        return pa.float64()
    if base in ("tinyint", "smallint", "mediumint", "int", "bigint"):
        return pa.int64()
    if base in ("date", "datetime", "timestamp"):
        return pa.timestamp("us")
    return pa.string()


def buildFeatherCache():
    sampleCols = None
    sampleParts: dict[str, pd.Series] = {}
    compressor = zstd.ZstdCompressor(level=3)

    CACHE_FEATHER_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmpNested = CACHE_NESTED_PATH.with_suffix(".tmp")
    tmpMain = CACHE_FEATHER_PATH.with_suffix(".tmp")

    writer = None
    sink = None
    schema = None
    total = 0
    try:
        with stocksEngine.connect() as conn:
            try:
                typeRows = conn.exec_driver_sql("SHOW COLUMNS FROM b3_stocks").fetchall()
                colTypes = {r[0]: str(r[1]).lower().split("(")[0].strip() for r in typeRows}
            except Exception:
                colTypes = {}
            stream = conn.execution_options(stream_results=True)
            result = stream.exec_driver_sql("SELECT * FROM b3_stocks")
            try:
                columns = list(result.keys())
                while True:
                    batch = result.fetchmany(2000)
                    if not batch:
                        break
                    chunk = pd.DataFrame.from_records((tuple(r) for r in batch), columns=columns)
                    if sampleCols is None:
                        sampleCols = [c for c in JSON_COLUMNS if c in chunk.columns]
                    for col in sampleCols or ():
                        if col not in sampleParts:
                            nonNull = chunk[col].dropna()
                            if not nonNull.empty:
                                sampleParts[col] = nonNull.head(20).reset_index(drop=True)
                        chunk[col] = chunk[col].map(
                            lambda s: compressor.compress(s.encode("utf-8")) if isinstance(s, str) else None
                        )
                    chunk = optimizeDtypes(chunk)

                    for col in CATEGORY_COLS:
                        if col in chunk.columns and str(chunk[col].dtype) == "category":
                            chunk[col] = chunk[col].astype(str)
                    if schema is None:
                        t0 = pa.Table.from_pandas(chunk, preserve_index=False)
                        fields = []
                        for n in t0.column_names:
                            t = t0.schema.field(n).type
                            if n in (sampleCols or ()):
                                fields.append(pa.field(n, pa.binary()))
                            elif pa.types.is_null(t):
                                fields.append(pa.field(n, arrowTypeFor(colTypes.get(n, "varchar"))))
                            else:
                                fields.append(pa.field(n, t))
                        schema = pa.schema(fields)
                        sink = pa.OSFile(str(tmpMain), "wb")
                        writer = pa.ipc.new_file(sink, schema)
                    table = pa.Table.from_pandas(chunk, schema=schema, preserve_index=False)
                    writer.write_table(table)
                    total += len(chunk)
                    del chunk, table
            finally:
                try:
                    result.close()
                except Exception:
                    pass
    finally:
        if writer is not None:
            writer.close()
        if sink is not None:
            sink.close()

    nestedSample = pd.DataFrame(sampleParts) if sampleParts else None
    if nestedSample is not None:
        nestedSample.to_feather(tmpNested)
        os.replace(tmpNested, CACHE_NESTED_PATH)
    if writer is not None:
        os.replace(tmpMain, CACHE_FEATHER_PATH)
        logger.info(f"feather written to {CACHE_FEATHER_PATH} ({total} records)")


def tryBuildLock():
    if fcntl is None:
        return open(os.devnull, "w")
    lockPath = CACHE_FEATHER_PATH.parent / "refresh.lock"
    try:
        lockPath.parent.mkdir(parents=True, exist_ok=True)
        lockFile = open(lockPath, "w")
    except OSError:
        # lock dir unavailable (e.g. read-only CI) — proceed unlocked; the build itself fails loudly if it cannot write
        return open(os.devnull, "w")
    try:
        fcntl.flock(lockFile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lockFile
    except OSError:
        lockFile.close()
        return None


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
                        )
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
