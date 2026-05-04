from collections import defaultdict
from fastapi import HTTPException
import pandas as pd

def categorizeColumns(columns: list) -> tuple:
    historicalFields: dict[str, list[int]] = defaultdict(list)
    fundamentalCols = []

    for col in columns:
        parts = col.split(" ")
        if len(parts) >= 2 and parts[-1].isdigit():
            year = int(parts[-1])
            field = " ".join(parts[:-1])
            historicalFields[field].append(year)
        else:
            if col not in ["TICKER", "NOME", "TIME"]:
                fundamentalCols.append(col)

    return dict(historicalFields), fundamentalCols

def parseYearInput(years: str) -> tuple:
    if not years:
        return None, None
    yearList = [int(y.strip()) for y in years.split(",")]
    if len(yearList) not in (1, 2):
        raise HTTPException(status_code=400, detail="Years format: YEAR or START_YEAR,END_YEAR")
    return yearList[0], yearList[0] if len(yearList) == 1 else yearList[1]

def normalizeColumns(data: pd.DataFrame, order: list) -> pd.DataFrame:
    existing_order = [col for col in order if col in data.columns]
    remaining = sorted(col for col in data.columns if col not in existing_order)
    return data[existing_order + remaining]