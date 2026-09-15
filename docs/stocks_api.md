# Brazilian Stocks Market API

API for Brazilian B3 stocks: year-based historicals, point-in-time fundamentals, 10-year daily cotations, and live B3 quotes. Built for the [Mansa](https://github.com/mansa-team) project and RAG integration.

Call `GET /stocks/fields` first — field names are dynamic. Never guess them.

## Usage

Environment configuration (`.env`):

```env
STOCKSAPI_ENABLED=TRUE
STOCKSAPI_HOST=localhost
STOCKSAPI_PORT=3200

STOCKSAPI_KEY.SYSTEM=FALSE
STOCKSAPI_PRIVATE.KEY=your_api_key_here
```

`KEY_SYSTEM` defaults to `False` (config.py:54). There are no `DEFAULT_QUOTA` / `RESETDAYS` vars. Quota is per-key: `requestLimit=100`, `currentUsage` (models/stocksapi_key.py:15).

## Auth

All data endpoints depend on `verifyAPIKey` (main/app/stocks_api/key.py:17) reading the `X-API-Key` header:

- `KEY_SYSTEM=false` → auth bypassed, dependency returns `None`.
- `KEY_SYSTEM=true` → missing key = `401`; unknown hash = `401`; usage over limit = `429`.
- Quota increment is one atomic `UPDATE ... WHERE currentUsage < requestLimit` (key.py:27-32); `rowcount == 0` decides 401 vs 429.

## API Endpoints

### Health Check

```bash
curl http://localhost:3200/stocks/health
```

Returns `status`, `service`, `cacheReady`, `cacheUpdatedAt`, `cacheAgeHours`.

### Field Discovery

```bash
curl http://localhost:3200/stocks/fields
```

Returns `historical` (field → years), `fundamental` (columns), `abbreviations`, `nested`. Returns `503` when the cache is not initialized (controller:72-73). No auth required.

### Historical Data

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/historical?search=PETR4&fields=LUCRO%20LIQUIDO&dates=2022,2024&orderBy=LUCRO%20LIQUIDO&limit=5"
```

- `search`: tickers only — regex `^[A-Za-z0-9,\s]*$` (controller:87), so no company-name free text. Case-insensitive, comma-separated, prefix match (`PET` matches `PETR4`, `PETR3`; query.py:153-168).
- `fields`: historical metric names WITHOUT year suffix; validated against `/fields`, invalid = `400`.
- `dates`: year-only. `2024` = that year; `2022,2024` = inclusive range. Full dates parse but only the year is used (query.py:195-200).
- Empty request (no `search`/`fields`/`dates`) → `400` (query.py:179-180).
- Columns come back as `"FIELD YEAR"` (e.g. `LUCRO LIQUIDO 2024`); rows deduped per ticker.
- Cache TTL `1h`, `Cache-Control: public, max-age=300` (controller:84,141).

### Fundamental Data

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/fundamental?search=VALE3&fields=ROE,P/L&dates=2024-06&orderBy=ROE&limit=10"
```

- `search`: same tickers-only regex + prefix match as historical. Empty/blank search dedups to one row per ticker (`drop_duplicates TICKER`, query.py:280-281).
- `fields`: point-in-time names, no year suffix. Cotation columns (`COTACAO 10Y PADRAO/AJUSTADA`) are excluded even if requested (query.py:245-256).
- `dates`: `YYYY` → last snapshot of the year; `YYYY-MM` → last of the month; `YYYY-MM-DD` → closest single snapshot per ticker (min-abs-diff grouping, query.py:262-275); `START,END` → range filter. Unparseable = `400`.
- Empty request (no `search`/`fields`/`dates`) → `400`.
- `TIME` normalized to `YYYY-MM-DD` (query.py:116-117).
- Cache TTL `5m`, `Cache-Control: public, max-age=300` (controller:149,211).

### Cotations (10-year daily history)

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/cotations?search=PETR4,VALE3&dates=2023-01-01,2023-12-31"
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/cotations?search=ITUB4&adjusted=true"
```

- `search` REQUIRED (min 1 char). Same ticker regex as above.
- `dates`: optional `YYYY-MM-DD,YYYY-MM-DD` filter on each `{DATA, PRECO}` entry; omitted = full 10-year series.
- `adjusted=false` → `COTACAO 10Y PADRAO` (nominal B3); `true` → `COTACAO 10Y AJUSTADA` (real returns).
- Sorted by `TIME` desc, deduped to latest row per ticker.
- Cache TTL `5m`, `Cache-Control: public, max-age=300` (controller:219,267).

### Live Price

```bash
curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/cotations/live?search=PETR4"
```

- `search` REQUIRED, single ticker, `max_length=7` (controller:278). Exact ticker — no prefix matching. B3 market hours 10:00–17:30 BRT; off-hours returns last close.
- Response `type: realtime-cotation` with `PRECO ATUAL/ORIGINAL/MINIMO/MAXIMO/MEDIO` + `timestamp`.
- Unknown ticker → `404`; B3 fetch failure → `503`. Transient (timeout/connection/5xx) retried 3x (query.py:341-347).
- Cache TTL `15s`, `Cache-Control: public, max-age=15` (controller:275,312).

### MCP (AI agent tools)

Mounted at `/stocks/mcp` via FastApiMCP (stocksapi_service.py:33-45) exposing 5 operations: `list_fields`, `get_historical`, `get_fundamental`, `get_cotations`, `get_live_price`.

`MCPDetectMiddleware` (stocksapi_service.py:10-22): any request with `X-MCP: true` forces `compact=true`. `?compact=true` (or the header) returns the abbreviated form: meta/historical/fundamental abbreviations, nested subfield compression, cotation `h`/`d` column form, live `PA/PO/PMN/PMX/PMD` keys, single-row `data` unwrapped, `count/search/fields/dates/type` stripped (compress.py).

## Response Format

```json
{
  "search": "PETR4",
  "fields": ["P/L", "ROE"],
  "dates": "2024-06",
  "type": "fundamental",
  "count": 1,
  "data": [{ "TICKER": "PETR4", "NOME": "...", "TIME": "2024-06-28", "P/L": 7.5, "ROE": 0.18 }]
}
```

`503 "Cache not initialized"` whenever the feather cache isn't loaded — guarded by `snapshot()` (query.py:55-64) and `/fields`.

## Architecture

- **Cache build**: feather written in 2000-row streaming batches; lost DB connections retried 3x on `OperationalError` (cache.py:71-77). Cross-process `fcntl` build lock with no-op fallback (`tryBuildLock`, cache.py:263,168-182); build runs in a `subprocess` (`sys.executable -c ... buildFeatherCache()`, cache.py:270-277). Nested JSON columns keep a 20-row decompressed sample (cache.py:108-113). Frame sorted `TICKER` asc / `TIME` desc (cache.py:185-192). Refresh every 12h, stale threshold 6h with background rebuild (cache.py:36,220-226).
- **Abbreviations**: `generateAbbreviations` with `dedupAbbrev` (util.py:47-53), meta `TK/NM/TI`; nested fields auto-detected with URL subfields dropped in compact (`detectNestedFields`, util.py:96-130).
- **Compact wire form**: cotations → `{"h": "D,P", "d": [...]}` with `DD-MM` dates and `K/M/B/T` ints (compress.py:100-109); live → `PA/PO/PMN/PMX/PMD` (compress.py:11-16).
- **Transport/caching**: `GZipMiddleware(minimum_size=4096, compresslevel=3)` (service:31); endpoint cache is `cashews` over `mem://` (controller:17) with TTLs above; `/fields` fetch from Prometheus side also retried 3x on transient (compact.py:77).

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
