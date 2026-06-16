import re
import calendar
from collections import defaultdict
from datetime import date

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


def normalizeColumns(data: pd.DataFrame, order: list) -> pd.DataFrame:
    existingOrder = [col for col in order if col in data.columns]
    remaining = sorted(col for col in data.columns if col not in existingOrder)
    return data[existingOrder + remaining]


def parseDateStart(dateStr: str) -> date:
    dateStr = dateStr.strip()
    if re.match(r"^\d{4}$", dateStr):
        return date(int(dateStr), 1, 1)
    if re.match(r"^\d{4}-\d{2}$", dateStr):
        parts = dateStr.split("-")
        return date(int(parts[0]), int(parts[1]), 1)
    return pd.to_datetime(dateStr).date()


def parseDateEnd(dateStr: str) -> date:
    dateStr = dateStr.strip()
    if re.match(r"^\d{4}$", dateStr):
        return date(int(dateStr), 12, 31)
    if re.match(r"^\d{4}-\d{2}$", dateStr):
        parts = dateStr.split("-")
        y, m = int(parts[0]), int(parts[1])
        lastDay = calendar.monthrange(y, m)[1]
        return date(y, m, lastDay)
    return pd.to_datetime(dateStr).date()


def parseDateRange(dates: str | None) -> tuple[date | None, date | None]:
    if not dates or not dates.strip():
        return None, None
    parts = [d.strip() for d in dates.split(",")]
    if len(parts) == 1:
        return parseDateStart(parts[0]), parseDateEnd(parts[0])
    if len(parts) == 2:
        return parseDateStart(parts[0]), parseDateEnd(parts[1])
    raise HTTPException(status_code=400, detail="Date format: DATE or START,END (max 2 values)")
