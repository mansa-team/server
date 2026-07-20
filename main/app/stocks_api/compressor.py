from __future__ import annotations

import re
from typing import Any

from main.app.stocks_api.cache import stocksCache
from main.app.stocks_api.util import generateAbbreviations, categorizeColumns, detectNestedFields

PRICE = {
    "PRECO ATUAL": "PA",
    "PRECO ORIGINAL": "PO",
    "PRECO MINIMO": "PMN",
    "PRECO MAXIMO": "PMX",
    "PRECO MEDIO": "PMD",
}
COT = {"DATA": "D", "PRECO": "P"}
SUF = [(1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")]
DF = re.compile(r"^\d{2}-\d{2}-(\d{4})$")
DI = re.compile(r"^(\d{4})-\d{2}-\d{2}$")

abbr: dict | None = None
nest: dict | None = None


def getAbbr() -> dict:
    global abbr
    if abbr is None:
        if stocksCache.STOCKS_CACHE is not None:
            h, f = categorizeColumns(stocksCache.STOCKS_CACHE.columns.tolist())
            abbr = generateAbbreviations(h, f)
        else:
            abbr = {"meta": {"TICKER": "TK", "NOME": "NM", "TIME": "TI"}, "historical": {}, "fundamental": {}}
    return abbr


def getNest() -> dict:
    global nest
    if nest is None:

        if stocksCache.STOCKS_CACHE is not None:
            nest = detectNestedFields(stocksCache.STOCKS_CACHE)
        else:
            nest = {}
    return nest


def rebuildAbbrevs() -> None:
    global abbr, nest
    abbr = nest = None


def walk(data: Any, fn: Any) -> Any:
    if isinstance(data, dict):
        return {k: walk(v, fn) for k, v in data.items()}
    if isinstance(data, list):
        return [walk(item, fn) for item in data]
    return fn(data)


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


def toColumnar(data: list) -> Any:
    if len(data) < 2 or not isinstance(data[0], dict):
        return data
    keys = list(data[0].keys())
    if not all(list(row.keys()) == keys for row in data):
        return data
    return {"h": ",".join(keys), "d": "\n".join("|".join(str(row[k]) for k in keys) for row in data)}


def fixHeaders(obj: Any) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "h" and isinstance(v, str):
                obj[k] = ",".join(COT.get(p.strip(), p.strip()) for p in v.split(","))
            elif isinstance(v, (dict, list)):
                fixHeaders(v)


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
        first = cd[0]
        if not isinstance(first, dict):
            return {"h": "v", "d": "\n".join("|".join(str(v) for v in x) for x in cd)}
        hdrs = list(first.keys())
        return {
            "h": ",".join(COT.get(h, h) for h in hdrs),
            "d": "\n".join("|".join(str(compactValue(x.get(h, ""))) for h in hdrs) for x in cd),
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


def compressResponse(raw: dict, tool: str, args: dict) -> dict:
    result = dict(raw)
    result.pop("count", None)
    for k in ("search", "fields", "dates"):
        if k in args and k in result:
            result.pop(k)
    result.pop("type", None)

    if tool == "get_cotations":
        result = compactCotations(result)
    elif tool == "get_live_price" and isinstance(result.get("data"), list):
        result["data"] = [
            {PRICE.get(k, k): v for k, v in x.items()} if isinstance(x, dict) else x for x in result["data"]
        ]

    d = result.get("data")
    if isinstance(d, list) and d and isinstance(d[0], dict):
        abbrs, nests = getAbbr(), getNest()
        result["data"] = [compactRow(row, tool, abbrs, nests) for row in d]
        result["data"] = walk(result["data"], compactValue)
        if isinstance(result["data"], list) and result["data"]:
            result["data"] = toColumnar(result["data"])
        if isinstance(result["data"], list) and len(result["data"]) == 1:
            result["data"] = result["data"][0]

    fixHeaders(result)
    return result
