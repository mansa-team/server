import re
import calendar
import json
from collections import defaultdict
from datetime import date
from typing import Any

from fastapi import HTTPException
import pandas as pd

JSON_COLUMNS = ("COTACAO 10Y PADRAO", "COTACAO 10Y AJUSTADA", "HISTORICO DIVIDENDOS", "NOTICIAS")

PREPOSITIONS = frozenset({"DE", "DO", "DA", "DOS", "DAS", "E", "O", "A", "EM", "COM", "POR", "PARA"})
URL_HINTS = frozenset({"link", "url", "href"})


def dedupAbbrev(used: set, abbrev: str) -> str:
    base, counter = abbrev, 2
    while abbrev in used:
        abbrev = f"{base}{counter}"
        counter += 1
    used.add(abbrev)
    return abbrev


def autoAbbreviate(name: str) -> str:
    name = name.strip()
    if len(name) <= 3 and " " not in name:
        return name.replace("/", "")
    if "/" in name:
        parts = [part.strip() for part in name.split("/") if part.strip()]
        if len(parts) <= 2:
            joined = "".join(parts)
            if len(joined) <= 5:
                return joined
        return "".join(part[0] for part in parts).upper()
    if "." in name:
        parts = [part.strip() for part in name.split(".") if part.strip()]
        if len(parts) >= 2:
            return "".join(part[0] for part in parts).upper()
    words = name.split()
    if len(words) >= 2:
        return "".join(
            word if word.isdigit() else word[0] for word in words if word.upper() not in PREPOSITIONS
        ).upper()
    return name[:3].upper() if len(name) > 3 else name.upper()


def generateAbbreviations(historical: dict, fundamental: list) -> dict:
    used: set[str] = set()
    return {
        "meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"},
        "historical": {field: dedupAbbrev(used, autoAbbreviate(field)) for field in historical},
        "fundamental": {field: dedupAbbrev(used, autoAbbreviate(field)) for field in fundamental},
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
        year, month = map(int, dateStr.split("-"))
        if end:
            return date(year, month, calendar.monthrange(year, month)[1])
        return date(year, month, 1)
    return date.fromisoformat(dateStr)


def parseDateRange(dates: str | None) -> tuple[date | None, date | None]:
    if not dates or not dates.strip():
        return None, None
    parts = [part.strip() for part in dates.split(",")]
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
        subfields = {key: dedupAbbrev(used, autoAbbreviate(key)) for key in keys}
        result[col] = {
            "subfields": subfields,
            "dropped_in_compact": [key for key in subfields if any(hint in key.lower() for hint in URL_HINTS)],
            "max_items_compact": 5 if len(keys) <= 4 else 15,
        }

    return result
