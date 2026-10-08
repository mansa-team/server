# bench_http.py — results 2026-10-08 (redis era, no restarts)

Targets: direct `http://localhost:3200` (STOCKSAPI_PORT) vs pooled
`http://localhost:8080` (NGINX_PORT). Read-only GETs, 200 reqs/level.
Raw samples: `scripts/bench_samples.jsonl` (3200 rows: target, level,
route, latency_ms, status, cache_status, t). Plots: `scripts/plots/`
via `python scripts/plot_bench.py` (no re-run needed to re-plot).

- Cached: `GET /stocks/fields` (~4.3 KB, `Cache-Control: public, max-age=21600`,
  no auth — KEY_SYSTEM=FALSE). Pooled: 800/800 `X-Cache-Status: HIT`.
- Uncached: `GET /user/health` (pooled: 800/800 BYPASS, no auth, no quota).

## /stocks/fields (cached) — p50 / p95 / rps

| level | direct          | pooled (HIT)    |
| ----- | --------------- | --------------- |
| c=10  | 65 / 122 ms / 124 | 17 / 44 ms / 384 |
| c=25  | 77 / 123 ms / 167 | 33 / 65 ms / 360 |
| c=50  | 81 / 103 ms / 168 | 34 / 56 ms / 381 |
| c=100 | 83 / 152 ms / 144 | 29 / 44 ms / 454 |

## /user/health (uncached bypass) — p50 / p95 / rps

| level | direct          | pooled (BYPASS) |
| ----- | --------------- | --------------- |
| c=10  | 37 / 64 ms / 210  | 35 / 57 ms / 209  |
| c=25  | 65 / 100 ms / 200 | 61 / 77 ms / 225  |
| c=50  | 55 / 104 ms / 226 | 58 / 109 ms / 212 |
| c=100 | 53 / 72 ms / 256  | 75 / 144 ms / 164 |

0 errors, no 5xx aborts on any level.

## Blink explanation

- Pooled HITs (17–34 ms p50, 360–454 rps, p95 ≤ 65 ms at every level)
  never touch the app; direct app-level redis hits cost 65–83 ms p50.
  Per-hit overhead of the redis path vs an nginx HIT: ~3–4× on p50.
- Bend point: the app cache path owns the tails. An earlier ladder on the
  same setup showed direct-fields p95 exploding to 849 ms at c=100 while
  the uncached path stayed flat (p95 104 ms); the re-run shows 152 ms.
  That run-to-run tail variance under concurrency isolates the bottleneck
  to the app cache path: single global cashews loop thread
  (`runOnCacheLoop` + `flightLock` in `main/utils/sync_cache.py`)
  serializing all redis TCP + pickle serde.
- The visible flash is MISS-vs-HIT variance plus slower app hits than the
  mem:// era (in-process dict, no TCP/serde/thread-hop). No container
  restarts were used; mem-era numbers are expectation, not measured.
- Caveat: stdlib urllib opens a new TCP connection per request (no
  keepalive), so absolute numbers include connect cost on both targets;
  the comparison is apples-to-apples.

## Plots

- `scripts/plots/p95_vs_concurrency.png` — p95 vs concurrency, both targets, both routes
- `scripts/plots/rps_vs_concurrency.png` — rps vs concurrency, both targets, both routes
- `scripts/plots/cdf_cached_c100.png` — latency CDF per target, cached route at c=100
