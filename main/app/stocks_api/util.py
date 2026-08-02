import re
import calendar
import json
from collections import defaultdict
from datetime import date
from typing import Any

import orjson
from fastapi import HTTPException
import pandas as pd

PREPOSITIONS = frozenset({"DE", "DO", "DA", "DOS", "DAS", "E", "O", "A", "EM", "COM", "POR", "PARA"})
URL_HINTS = frozenset({"link", "url", "href"})


def dedupAbbrev(used: set, abbrev: str) -> str:
    base, n = abbrev, 2
    while abbrev in used:
        abbrev = f"{base}{n}"
        n += 1
    used.add(abbrev)
    return abbrev


def autoAbbreviate(name: str) -> str:
    name = name.strip()
    if len(name) <= 3 and " " not in name:
        return name.replace("/", "")
    if "/" in name:
        parts = [p.strip() for p in name.split("/") if p.strip()]
        if len(parts) <= 2:
            joined = "".join(parts)
            if len(joined) <= 5:
                return joined
        return "".join(p[0] for p in parts).upper()
    if "." in name:
        parts = [p.strip() for p in name.split(".") if p.strip()]
        if len(parts) >= 2:
            return "".join(p[0] for p in parts).upper()
    words = name.split()
    if len(words) >= 2:
        return "".join(w if w.isdigit() else w[0] for w in words if w.upper() not in PREPOSITIONS).upper()
    return name[:3].upper() if len(name) > 3 else name.upper()


def generateAbbreviations(historical: dict, fundamental: list) -> dict:
    used: set[str] = set()
    return {
        "meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"},
        "historical": {f: dedupAbbrev(used, autoAbbreviate(f)) for f in historical},
        "fundamental": {f: dedupAbbrev(used, autoAbbreviate(f)) for f in fundamental},
    }


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


def parseDate(dateStr: str, end: bool = False) -> date:
    dateStr = dateStr.strip()
    if re.match(r"^\d{4}$", dateStr):
        return date(int(dateStr), 12, 31) if end else date(int(dateStr), 1, 1)
    if re.match(r"^\d{4}-\d{2}$", dateStr):
        y, m = map(int, dateStr.split("-"))
        if end:
            return date(y, m, calendar.monthrange(y, m)[1])
        return date(y, m, 1)
    return pd.to_datetime(dateStr).date()


def parseDateRange(dates: str | None) -> tuple[date | None, date | None]:
    if not dates or not dates.strip():
        return None, None
    parts = [d.strip() for d in dates.split(",")]
    if len(parts) == 1:
        return parseDate(parts[0], end=False), parseDate(parts[0], end=True)
    if len(parts) == 2:
        return parseDate(parts[0], end=False), parseDate(parts[1], end=True)
    raise HTTPException(status_code=400, detail="Date format: DATE or START,END (max 2 values)")


def detectNestedFields(df: pd.DataFrame) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    skip = {"TICKER", "NOME", "TIME"}

    for col in df.columns:
        if col in skip or df[col].dtype not in ("object", "string", "string[pyarrow]"):
            continue

        sample = df[col].head(5).dropna()
        if not sample.size:
            continue

        keys: set[str] = set()
        for item in sample:
            try:
                parsed = json.loads(item) if isinstance(item, str) else item
            except (ValueError, TypeError):
                continue
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                for row in parsed:
                    if isinstance(row, dict):
                        keys.update(row.keys())

        if not keys:
            continue

        used: set[str] = set()
        subfields = {k: dedupAbbrev(used, autoAbbreviate(k)) for k in keys}
        result[col] = {
            "subfields": subfields,
            "dropped_in_compact": [k for k in subfields if any(t in k.lower() for t in URL_HINTS)],
            "max_items_compact": 5 if len(keys) <= 4 else 15,
        }

    return result
