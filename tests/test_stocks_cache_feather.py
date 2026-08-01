import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from main.app.stocks_api.cache import COMPRESS_COLS, StocksCacheManager, optimizeDtypes


def test_optimize_dtypes_skips_pyarrow_for_compress_cols():
    df = pd.DataFrame(
        {
            "TICKER": ["PETR4", "VALE3"],
            "COTACAO 10Y PADRAO": ['{"DATA": "x"}', '{"DATA": "y"}'],
            "NOME": ["PETROBRAS", "VALE"],
        }
    )
    result = optimizeDtypes(df)
    assert str(result["COTACAO 10Y PADRAO"].dtype) == "object"
    assert str(result["NOME"].dtype) == "category"
