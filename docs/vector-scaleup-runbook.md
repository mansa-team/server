# Vector Scale-Up Runbook

One-page guide for migrating Prometheus vector search off in-process brute force
(MySQL 8.0, no `VECTOR()` syntax) when scale demands it.

## Baseline (lane 4)

- `search()` latency ~0.2-0.6 ms at N=50-500 rows (in-process normalize + dot product).
- `decodeEmbeddings()` cost flat across N=50-500 (BLOB join + reshape, no per-row query).
- Prefilter cap `MEMORY_SEARCH_PREFILTER_CAP = 500` bounds per-query decode work.

## Move triggers (any one fires the migration)

1. Single-user active rows > 100k.
2. Search p95 > 500 ms at 500 rows in the lane-4 bench.
3. Hosting move to OCI (HeatWave available).

## Options

| Option | Change | When |
|---|---|---|
| HeatWave | `DISTANCE()` + `VECTOR INDEX`, zero code change beyond SQL | On OCI with HeatWave |
| Qdrant sidecar | Export via `toVectorString`, dual-write during cutover | Self-hosted, need ANN index |
| MySQL 9 native | Only when Community ships an index (tracked in mysql-server#708, not delivered) | Not yet — do not plan on it |

## Export recipe

1. Select id + embedding per row; serialize each with
   `main/app/prometheus/vector.py:toVectorString` (`"[0.1,0.2,...]"` format).
2. Bulk-load strings to target (HeatWave `STRING_TO_VECTOR()` or Qdrant upsert).
3. Parity-check: top-10 overlap on 20 probe queries against brute-force results.
4. Cutover: Qdrant path dual-writes during migration, then flips reads.
