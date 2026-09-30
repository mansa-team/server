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
DF = re.compile(r"^\d{2}-\d{2}-(\d{4})$")
DI = re.compile(r"^(\d{4})-\d{2}-\d{2}$")

ABBR_FALLBACK = {"meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"}, "historical": {}, "fundamental": {}}

_abbrFrame: pd.DataFrame | None = None
_abbrValue: dict | None = None
_nestFrame: pd.DataFrame | None = None
_nestSample: pd.DataFrame | None = None
_nestValue: dict | None = None


def getAbbr(df: pd.DataFrame | None = None) -> dict:
    """Abbreviation map for a frame (dependency-injected; no cache import).

    Results are memoized by frame identity (strong refs, `is` comparison —
    DataFrames are unhashable so lru_cache cannot key on them). Pass None
    for the meta-only fallback. Call rebuildAbbrevs() after the feather
    frame is replaced, same as before.
    """
    global _abbrFrame, _abbrValue
    if _abbrValue is not None and _abbrFrame is df:
        return _abbrValue
    if df is not None:
        h, f = categorizeColumns(df.columns.tolist())
        value = generateAbbreviations(h, f)
    else:
        value = {"meta": dict(ABBR_FALLBACK["meta"]), "historical": {}, "fundamental": {}}
    _abbrFrame, _abbrValue = df, value
    return value


def getNest(df: pd.DataFrame | None = None, nestedSample: pd.DataFrame | None = None) -> dict:
    """Nested-field map for a frame plus its nested sample (same memo policy)."""
    global _nestFrame, _nestSample, _nestValue
    if _nestValue is not None and _nestFrame is df and _nestSample is nestedSample:
        return _nestValue
    if df is not None:
        nest = detectNestedFields(df)
        if nestedSample is not None:
            for col, info in detectNestedFields(nestedSample).items():
                nest.setdefault(col, info)
        value = nest
    else:
        value = {}
    _nestFrame, _nestSample, _nestValue = df, nestedSample, value
    return value


def rebuildAbbrevs() -> None:
    global _abbrFrame, _abbrValue, _nestFrame, _nestSample, _nestValue
    _abbrFrame, _abbrValue = None, None
    _nestFrame, _nestSample, _nestValue = None, None, None


def compactValue(v: Any) -> Any:
    if isinstance(v, float):
        v = float(f"{v:.10g}")
    if isinstance(v, int) and not isinstance(v, bool):
        for t, s in SUF:
            if abs(v) >= t:
                q = v / t
                v = f"{int(q)}{s}" if q == int(q) else f"{q:.1f}{s}"
                break
    if isinstance(v, str):
        m = DF.match(v)
        if m:
            dd, rest = v.split("-", 1)
            return f"{rest.split('-', 1)[0]}-{dd}"
        m = DI.match(v)
        if m:
            p = v.split("-")
            return f"{p[1]}-{p[2]}"
    return v


def compactRow(row: dict, tool: str, abbrs: dict, nests: dict) -> dict:
    m, h, f = abbrs["meta"], abbrs["historical"], abbrs["fundamental"]
    out = {}
    for k, v in row.items():
        if k in m:
            out[m[k]] = v
        elif tool == "get_historical" and " " in k and k[-4:].isdigit():
            base, year = k.rsplit(" ", 1)
            a = h.get(base) or "".join(w[0] for w in base.split() if w)
            out[f"{a}.{year[-2:]}"] = v
        elif k in f:
            out[f[k]] = v
        else:
            out[k] = v

    for field, spec in nests.items():
        if field in out and isinstance(out[field], list):
            km = spec["subfields"]
            dr = set(spec.get("dropped_in_compact", []))
            mx = spec.get("max_items_compact", 15)
            out[field] = [
                {km.get(k, k): v for k, v in x.items() if k not in dr} if isinstance(x, dict) else x
                for x in out[field][:mx]
            ]

    return out


def compactCotations(result: dict) -> dict:
    data = result.get("data")
    if not isinstance(data, list):
        return result

    def toCol(cd: list) -> dict:
        cot = {"DATA": "D", "PRECO": "P"}
        first = cd[0]
        if not isinstance(first, dict):
            return {"h": "v", "d": ["|".join(str(v) for v in x) for x in cd]}
        hdrs = list(first.keys())
        return {
            "h": ",".join(cot.get(h, h) for h in hdrs),
            "d": ["|".join(str(compactValue(x.get(h, ""))) for h in hdrs) for x in cd],
        }

    if len(data) == 1 and isinstance(data[0], dict):
        entry = data[0]
        ck = next((k for k in entry if k.startswith("COTACAO")), None)
        if ck and isinstance(entry[ck], list) and entry[ck]:
            result["TK"] = entry.get("TICKER", entry.get("TK", ""))
            result["NM"] = entry.get("NOME", entry.get("NM", ""))
            result["TI"] = compactValue(entry.get("TIME", entry.get("TI", "")))
            result["C10" if "10Y" in ck else ck[:4]] = toCol(entry[ck])
            result.pop("data", None)
            return result

    for i, entry in enumerate(data):
        if isinstance(entry, dict):
            ck = next((k for k in entry if k.startswith("COTACAO")), None)
            if ck and isinstance(entry[ck], list) and entry[ck]:
                result["data"][i] = {**entry, ck: toCol(entry[ck])}
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
    for k in ("search", "fields", "dates"):
        if k in args and k in result:
            result.pop(k)
    result.pop("type", None)

    if tool == "get_cotations":
        return compactCotations(result)
    elif tool == "get_live_price" and isinstance(result.get("data"), list):
        result["data"] = [
            {PRICE.get(k, k): v for k, v in x.items()} if isinstance(x, dict) else x for x in result["data"]
        ]

    d = result.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict):
        abbrs, nests = getAbbr(df), getNest(df, nestedSample)
        result["data"] = [compactRow(row, tool, abbrs, nests) for row in d]

        def compactLeaves(v: Any) -> Any:
            if isinstance(v, dict):
                return {k: compactLeaves(x) for k, x in v.items()}
            if isinstance(v, list):
                return [compactLeaves(x) for x in v]
            return compactValue(v)

        result["data"] = compactLeaves(result["data"])
        if isinstance(result["data"], list) and len(result["data"]) == 1:
            result["data"] = result["data"][0]
    return result
