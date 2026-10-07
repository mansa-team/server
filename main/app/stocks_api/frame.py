import logging

import pandas as pd
import pyarrow as pa

from main.app.stocks_api.util import JSON_COLUMNS

logger = logging.getLogger(__name__)

CATEGORY_COLS = frozenset(["TICKER", "NOME"])
PRESORTED_FLAG_KEY = b"b3_presorted"


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
    except (TypeError, ValueError, AttributeError) as e:
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


def sortCacheFrame(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "TIME" not in df.columns or "TICKER" not in df.columns:
        return df
    try:
        return df.sort_values(by=["TICKER", "TIME"], ascending=[True, False], kind="mergesort").reset_index(drop=True)
    except TypeError:
        logger.warning("sortCacheFrame: mixed TIME dtypes, keeping load order")
        return df.reset_index(drop=True)


def buildTickerIndex(df: pd.DataFrame) -> dict:
    index = {}
    for idx, ticker in enumerate(df["TICKER"]):
        key = str(ticker).upper()
        if key not in index:
            index[key] = idx
    return index
