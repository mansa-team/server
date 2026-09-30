"""Feather build / read helpers for the stocks cache.

Owns the on-disk layout (CACHE_*_PATH) and the DB-to-feather build.
Imports from frame.py only — never from cache.py at module load, so the
load-time graph stays acyclic (cache -> build -> frame).

Runtime config (engine + paths) is resolved via the cache module at call
time (_runtimeConf): tests rebind stocksEngine / CACHE_*_PATH on
main.app.stocks_api.cache, and reading them there keeps those patch
sites working with zero behavior change in production.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.feather as feather
import zstandard as zstd
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from config import stocksEngine as _fallbackStocksEngine
from main.app.stocks_api.frame import (
    CATEGORY_COLS,
    PRESORTED_FLAG_KEY,
    arrowTypeFor,
    optimizeDtypes,
)
from main.app.stocks_api.util import JSON_COLUMNS

fcntl: Any = None
if sys.platform != "win32":
    import fcntl

logger = logging.getLogger(__name__)

CACHE_FEATHER_PATH = Path("/app/cache/stocks_cache.feather")
CACHE_NESTED_PATH = Path("/app/cache/stocks_nested.feather")


def _runtimeConf() -> tuple:
    """Return (engine, featherPath, nestedPath), preferring live values on
    the cache module (where tests monkeypatch) over this module's defaults."""
    import main.app.stocks_api.cache as cacheMod

    engine = getattr(cacheMod, "stocksEngine", None) or _fallbackStocksEngine
    featherPath = getattr(cacheMod, "CACHE_FEATHER_PATH", CACHE_FEATHER_PATH)
    nestedPath = getattr(cacheMod, "CACHE_NESTED_PATH", CACHE_NESTED_PATH)
    return engine, featherPath, nestedPath


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(),
    retry=retry_if_exception_type(OperationalError),
    reraise=True,
)
def buildFeatherCache(engine: Engine | None = None):
    sampleCols = None
    sampleParts: dict[str, pd.Series] = {}
    compressor = zstd.ZstdCompressor(level=3)

    defaultEngine, featherPath, nestedPath = _runtimeConf()
    featherPath.parent.mkdir(parents=True, exist_ok=True)
    tmpNested = nestedPath.with_suffix(".tmp")
    tmpMain = featherPath.with_suffix(".tmp")

    writer = None
    sink = None
    schema = None
    total = 0
    resolvedEngine = engine if engine is not None else defaultEngine
    try:
        with resolvedEngine.connect() as conn:
            try:
                typeRows = conn.exec_driver_sql("SHOW COLUMNS FROM b3_stocks").fetchall()
                colTypes = {r[0]: str(r[1]).lower().split("(")[0].strip() for r in typeRows}
            except Exception:
                colTypes = {}
            stream = conn.execution_options(stream_results=True)
            result = stream.exec_driver_sql("SELECT * FROM b3_stocks ORDER BY TICKER ASC, TIME DESC")
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
                        schema = pa.schema(fields).with_metadata({PRESORTED_FLAG_KEY: b"1"})
                        sink = pa.OSFile(str(tmpMain), "wb")
                        writer = pa.ipc.new_file(sink, schema)
                    assert writer is not None  # nosec: B101 mypy narrowing, writer assigned just above
                    table = pa.Table.from_pandas(chunk, schema=schema, preserve_index=False)
                    writer.write_table(table)
                    total += len(chunk)
                    del chunk, table
            finally:
                try:
                    result.close()
                except Exception:
                    pass  # nosec: B110 best-effort writer/sink close, retried next refresh
    except OperationalError:
        logger.warning("feather build lost connection, retrying with fresh connection")
        try:
            resolvedEngine.dispose()
        except Exception:
            pass  # nosec: B110 dispose is best-effort, original error re-raised below
        raise
    finally:
        if writer is not None:
            writer.close()
        if sink is not None:
            sink.close()

    nestedSample = pd.DataFrame(sampleParts) if sampleParts else None
    if nestedSample is not None:
        nestedSample.to_feather(tmpNested)
        os.replace(tmpNested, nestedPath)
    if writer is not None:
        os.replace(tmpMain, featherPath)
        logger.info(f"feather written to {featherPath} ({total} records)")


def tryBuildLock():
    if fcntl is None:
        return open(os.devnull, "w")
    _, featherPath, _ = _runtimeConf()
    lockPath = featherPath.parent / "refresh.lock"
    try:
        lockPath.parent.mkdir(parents=True, exist_ok=True)
        lockFile = open(lockPath, "w")
    except OSError:
        return open(os.devnull, "w")
    try:
        fcntl.flock(lockFile, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lockFile
    except OSError:
        lockFile.close()
        return None


def readFeatherDataFrame(path: Path) -> tuple[pd.DataFrame, bool]:
    table = feather.read_table(path, memory_map=True)
    presorted = (table.schema.metadata or {}).get(PRESORTED_FLAG_KEY) == b"1"
    df = table.to_pandas(split_blocks=True, types_mapper=pd.ArrowDtype)
    return df, presorted
