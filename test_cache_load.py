import sys
import traceback

sys.stderr = sys.stdout

try:
    from config import stocksEngine
    import pandas as pd
    import numpy as np
    from main.app.stocks_api.cache import optimizeDtypes

    df = pd.read_sql("SELECT * FROM b3_stocks", stocksEngine)
    print(f"Loaded {len(df)} rows, {len(df.columns)} cols")
    print(f"Memory before: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

    df = df.replace({np.nan: None, np.inf: None, -np.inf: None})
    print(f"After replace: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

    df = optimizeDtypes(df)
    print(f"After optimize: {df.memory_usage(deep=True).sum() / 1024 / 1024:.1f} MB")

    if "TIME" in df.columns:
        print(f"TIME dtype: {df['TIME'].dtype}")
        sample = df["TIME"].head(3).tolist()
        print(f"TIME samples: {sample}")

    # Test serialization
    import orjson
    from main.app.stocks_api.query import sanitizeNanValues

    records = df.head(5).to_dict(orient="records")
    sanitized = sanitizeNanValues(records)
    serialized = orjson.dumps(sanitized)
    print(f"Serialization OK: {len(serialized)} bytes")
    print("SUCCESS")
except Exception as e:
    traceback.print_exc()
    print(f"FAILED: {e}")
