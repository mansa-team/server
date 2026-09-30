from __future__ import annotations

import re
from typing import Any

import pandas as pd

from main.app.stocks_api.util import generateAbbreviations, categorizeColumns, detectNestedFields

PRICE = {
    "PRECO ATUAL": "PA",
    "PRECO ORIGINAL": "PO",
    "PRECO MINIMO": "PMN",
    "PRECO MAXIMO": "PMX",
    "PRECO MEDIO": "PMD",
}
SUF = [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]
DMY_DATE = re.compile(r"^\d{2}-\d{2}-(\d{4})$")
ISO_DATE = re.compile(r"^(\d{4})-\d{2}-\d{2}$")

ABBR_FALLBACK = {"meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"}, "historical": {}, "fundamental": {}}

abbrFrame: pd.DataFrame | None = None
abbrValue: dict | None = None
nestFrame: pd.DataFrame | None = None
nestSample: pd.DataFrame | None = None
nestValue: dict | None = None


def getAbbr(df: pd.DataFrame | None = None) -> dict:
    global abbrFrame, abbrValue
    if abbrValue is not None and abbrFrame is df:
        return abbrValue
    if df is not None:
        historical, fundamental = categorizeColumns(df.columns.tolist())
        value = generateAbbreviations(historical, fundamental)
    else:
        value = {"meta": dict(ABBR_FALLBACK["meta"]), "historical": {}, "fundamental": {}}
    abbrFrame, abbrValue = df, value
    return value


def getNest(df: pd.DataFrame | None = None, nestedSample: pd.DataFrame | None = None) -> dict:
    global nestFrame, nestSample, nestValue
    if nestValue is not None and nestFrame is df and nestSample is nestedSample:
        return nestValue
    if df is not None:
        nest = detectNestedFields(df)
        if nestedSample is not None:
            for col, info in detectNestedFields(nestedSample).items():
                nest.setdefault(col, info)
        value = nest
    else:
        value = {}
    nestFrame, nestSample, nestValue = df, nestedSample, value
    return value


def rebuildAbbrevs() -> None:
    global abbrFrame, abbrValue, nestFrame, nestSample, nestValue
    abbrFrame, abbrValue = None, None
    nestFrame, nestSample, nestValue = None, None, None


def compactValue(value: Any) -> Any:
    if isinstance(value, float):
        value = float(f"{value:.10g}")
    if isinstance(value, int) and not isinstance(value, bool):
        for threshold, suffix in SUF:
            if abs(value) >= threshold:
                quotient = value / threshold
                value = f"{int(quotient)}{suffix}" if quotient == int(quotient) else f"{quotient:.1f}{suffix}"
                break
    if isinstance(value, str):
        match = DMY_DATE.match(value)
        if match:
            day, rest = value.split("-", 1)
            return f"{rest.split('-', 1)[0]}-{day}"
        match = ISO_DATE.match(value)
        if match:
            parts = value.split("-")
            return f"{parts[1]}-{parts[2]}"
    return value


def compactRow(row: dict, tool: str, abbrs: dict, nests: dict) -> dict:
    meta, historical, fundamental = abbrs["meta"], abbrs["historical"], abbrs["fundamental"]
    out = {}
    for key, value in row.items():
        if key in meta:
            out[meta[key]] = value
        elif tool == "get_historical" and " " in key and key[-4:].isdigit():
            base, year = key.rsplit(" ", 1)
            abbrev = historical.get(base) or "".join(word[0] for word in base.split() if word)
            out[f"{abbrev}.{year[-2:]}"] = value
        elif key in fundamental:
            out[fundamental[key]] = value
        else:
            out[key] = value

    for field, spec in nests.items():
        if field in out and isinstance(out[field], list):
            submap = spec["subfields"]
            dropped = set(spec.get("dropped_in_compact", []))
            maxItems = spec.get("max_items_compact", 15)
            out[field] = [
                {submap.get(key, key): value for key, value in item.items() if key not in dropped}
                if isinstance(item, dict)
                else item
                for item in out[field][:maxItems]
            ]

    return out


def compactCotations(result: dict) -> dict:
    data = result.get("data")
    if not isinstance(data, list):
        return result

    def toCol(entries: list) -> dict:
        cot = {"DATA": "D", "PRECO": "P"}
        first = entries[0]
        if not isinstance(first, dict):
            return {"h": "v", "d": ["|".join(str(value) for value in entry) for entry in entries]}
        hdrs = list(first.keys())
        return {
            "h": ",".join(cot.get(header, header) for header in hdrs),
            "d": ["|".join(str(compactValue(entry.get(header, ""))) for header in hdrs) for entry in entries],
        }

    if len(data) == 1 and isinstance(data[0], dict):
        entry = data[0]
        cotationKey = next((key for key in entry if key.startswith("COTACAO")), None)
        if cotationKey and isinstance(entry[cotationKey], list) and entry[cotationKey]:
            result["TK"] = entry.get("TICKER", entry.get("TK", ""))
            result["NM"] = entry.get("NOME", entry.get("NM", ""))
            result["TI"] = compactValue(entry.get("TIME", entry.get("TI", "")))
            result["C10" if "10Y" in cotationKey else cotationKey[:4]] = toCol(entry[cotationKey])
            result.pop("data", None)
            return result

    for index, entry in enumerate(data):
        if isinstance(entry, dict):
            cotationKey = next((key for key in entry if key.startswith("COTACAO")), None)
            if cotationKey and isinstance(entry[cotationKey], list) and entry[cotationKey]:
                result["data"][index] = {**entry, cotationKey: toCol(entry[cotationKey])}
    return result


def compressResponse(
    raw: dict,
    tool: str,
    args: dict,
    df: pd.DataFrame | None = None,
    nestedSample: pd.DataFrame | None = None,
) -> dict:
    result = dict(raw)
    result.pop("count", None)
    for key in ("search", "fields", "dates"):
        if key in args and key in result:
            result.pop(key)
    result.pop("type", None)

    if tool == "get_cotations":
        return compactCotations(result)
    elif tool == "get_live_price" and isinstance(result.get("data"), list):
        result["data"] = [
            {PRICE.get(key, key): value for key, value in row.items()} if isinstance(row, dict) else row
            for row in result["data"]
        ]

    rows = result.get("data")
    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
        abbrs, nests = getAbbr(df), getNest(df, nestedSample)
        result["data"] = [compactRow(row, tool, abbrs, nests) for row in rows]

        def compactLeaves(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: compactLeaves(item) for key, item in value.items()}
            if isinstance(value, list):
                return [compactLeaves(item) for item in value]
            return compactValue(value)

        result["data"] = compactLeaves(result["data"])
        if isinstance(result["data"], list) and len(result["data"]) == 1:
            result["data"] = result["data"][0]
    return result
