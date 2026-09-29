# nginx Scaling Plan — reverse proxy + response cache for `/stocks`, and the multi-server evolution

**Status:** PLAN ONLY — nothing in this document is implemented. No application, compose, or nginx file was modified.
**Produced by:** swarm `swarm/nginx-scaling` (board root `ses_f178f53fdffeEz0Nswxk4ay80O`), 3 lanes merged by prime:
- L1 `calm-amber-tiger` (code-architect) — implementation plan
- L2 `keen-coral-badger` (general) — benchmark plan
- L3 `keen-coral-otter` (code-architect) — future scaling + risk register

Lanes ran read-only (no write/board/skill tools in that lane toolset), so prime relayed their envelopes to the board and merged their full drafts here. Evidence was read directly from source by the lanes; prime's own earlier eval corroborates the TTL map.

## 0. Purpose and constraints

**Goal:** put nginx in front of `/stocks` as reverse proxy + response cache so a cache HIT never enters Python (no uvicorn routing, no `verifyAPIKey` DB scan+UPDATE, no pandas, no ORJSON serialization, no shared-GIL contention), while staying consistent with the planned multi-server future.

**Constraint traceability (TODO.md → this document):**

| TODO.md | Constraint | Covered in |
|---|---|---|
| line 11 | nginx scaling for autoscaling workers, tailored configs triggering only required services, remote VPS support | §1 P2/P3, §3.2, §3.3, §3.7 |
| line 12 | ForgeVM multi-host scaling, router in business code, hostId tracking, rclone for /workspace | §3.8 |
| line 13 | drop `{service}_HOST`/`{service}_PORT`, replace with nginx-managed services | §1 P4, §3.4 |
| line 14 | p99 latency + context switches monitored at `/status` | §2.5, §2.8 (feed), §3.10 step |
| line 15 | feather cache synced + Redis as flock replacement | §1 P4, §3.5a, §3.6 |
| lines 16–17 | anti-scraping (single-tab cookie session; random UUID routing) | §1 §9, §3.9 R4/R5 |
| lines 47–70 | rate limits 30 rpm (STARTUP) / 300 rpm (ENTERPRISE), 10k calls/month STARTUP | §1 §8, §3.5b, §3.9 R2/R8 |

**Verified ground truth (source, this session):** see §3.0. Key items: all three services default `PORT=3200` (`config.py:41,53,62`), one process/one GIL (`service_manager.py:49-51`), endpoint cache is in-process cashews `mem://` (`stocksapi_controller.py:17`), feather rebuild every 12h with per-host `flock` (`cache.py:179,221-227`), `X-MCP` header mutates the body via `MCPDetectMiddleware` (`stocksapi_service.py:10-22`).

---

# Part 1 — Implementation plan

## 1.1 Architecture decision

nginx 1.27-alpine as a first-class compose service, disk-backed `proxy_cache` keyed on `$http_x_api_key` + `$http_x_mcp` + `$request_uri`, one `upstream` per logical service, `proxy_cache_lock` + `background_update` so concurrent misses collapse to one origin call. Only GET `/stocks/*` is cached; `/stocks/health` and `/stocks/mcp` bypass.

Why: removes the GIL/uvicorn/serialization/quota-DB cost for the dominant read workload with zero new application code (cache, keepalive, gzip, rate limiting all ship with nginx). The cache sits in front, so it is orthogonal to the worker-container split (P2) and remote VPS fan-out (P3) — the same `upstream` block just gains `server` lines.

Accepted trade-offs:
- Quota counts misses only (hit-heavy clients under-count) — see §1.8; billing rule decision required.
- Per-key cache fragmentation: one entry per `(key, x-mcp, uri)`.
- OSS nginx has no active health checks → passive `max_fails`/`fail_timeout` only (§1.6).

Rejected: app-level cache only (defeats the goal); Varnish (extra moving part for a feature nginx already has); CDN (not the self-hosted model; TODO-11 explicitly wants nginx).

## 1.2 File layout

**Create:**
```
nginx/
  conf.d/
    00-http-common.conf      # http-context: proxy_cache_path, limit_req_zone, gzip, log_format
    10-upstreams.conf        # upstream stocks_api (+ remote servers in P3)
    20-stocks-cache.conf     # server :80 -> cache locations
  snippets/
    stocks-proxy.conf        # shared proxy_* directives for cached locations
    stocks-bypass.conf       # proxy without cache (health, mcp, everything else)
```
**Modify:** `docker-compose.yml` (P0 add nginx service; P2 ports + worker profile), `config.py` (P2 distinct port defaults; P4 `ROUTING_MODE` design), `.env.example`/`README.md` (P2), `main/app/stocks_api/key.py` + `main/utils/logging_config.py` (P4 design only).

Mounting `conf.d/` + `snippets/` keeps the stock `nginx.conf` (and its `include /etc/nginx/conf.d/*.conf` inside `http{}`) — no need to replace `nginx.conf`.

## 1.3 Phase P0 — nginx service + config skeleton

```yaml
  nginx:
    image: nginx:1.27-alpine
    restart: always
    ports: ["80:80"]
    volumes:
      - ./nginx/conf.d:/etc/nginx/conf.d:ro
      - ./nginx/snippets:/etc/nginx/snippets:ro
      - nginx-cache:/var/cache/nginx
    depends_on: [api]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost/nginx-health"]
      interval: 10s
      timeout: 3s
      retries: 3
volumes:
  nginx-cache:
```

`00-http-common.conf` (http context):
```nginx
proxy_cache_path /var/cache/nginx/stocks
    levels=1:2 keys_zone=stocks_cache:64m
    max_size=2g inactive=2h use_temp_path=off;

limit_req_zone $http_x_api_key zone=stocks_key:10m rate=300r/m;
limit_req_status 429;

log_format cache '$remote_addr "$request" $status $body_bytes_sent '
                 'cache=$upstream_cache_status key=${http_x_api_key:0:8} '
                 'rt=$request_time urt=$upstream_response_time';
access_log /var/log/nginx/access.log cache;

gzip on; gzip_comp_level 3; gzip_min_length 1024;
gzip_proxied any; gzip_vary on; gzip_types application/json;

server { listen 80; location = /nginx-health { return 200 "ok\n"; } }
```
Sizing: ~1 MB `keys_zone` per ~8k keys → 64 MB ≫ expected; `max_size 2g` bounds disk; `inactive 2h` > max TTL (1h).

`10-upstreams.conf`:
```nginx
upstream stocks_api {
    least_conn;
    server api:3200 max_fails=3 fail_timeout=10s;
    keepalive 32;              # requires proxy_http_version 1.1 + Connection ""
    keepalive_timeout 60s;
    keepalive_requests 1000;
}
```

**Verify P0:** `docker compose config` parses; `curl -sI http://localhost/nginx-health` → 200; `curl -sD- -o/dev/null http://localhost/stocks/health -H "X-API-Key: $K"` reaches the app (200) with cache not yet asserted.
**Rollback:** bring compose up without `nginx`; nothing else changed.

## 1.4 Phase P1 — cache locations, TTL table, directives

`snippets/stocks-proxy.conf`:
```nginx
proxy_pass http://stocks_api;
proxy_http_version 1.1;
proxy_set_header Connection "";
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Accept-Encoding "";          # gzip at nginx only — no double compression

proxy_cache stocks_cache;
proxy_cache_key "s:$http_x_api_key:$http_x_mcp:$request_uri";
proxy_cache_lock on;
proxy_cache_lock_timeout 20s;
proxy_cache_background_update on;
proxy_cache_revalidate on;
proxy_cache_use_stale updating error timeout http_500 http_502 http_503 http_504;
proxy_ignore_headers Cache-Control Expires Set-Cookie;

# cache only 2xx; 401/429/5xx pass through and are never stored
proxy_cache_valid 401 429 0s;
proxy_cache_valid any 0s;

proxy_buffering on;
proxy_buffers 8 32k;
proxy_busy_buffers_size 64k;
proxy_max_temp_file_size 512m;
add_header X-Cache-Status $upstream_cache_status always;
```

`20-stocks-cache.conf` (exact `=` locations so `/cotations/live` cannot be captured by `/cotations`):
```nginx
server {
    listen 80;

    location = /stocks/health  { include snippets/stocks-bypass.conf; }
    location   /stocks/mcp     { include snippets/stocks-bypass.conf; }

    location = /stocks/cotations/live {
        limit_req zone=stocks_key burst=50 nodelay;
        include snippets/stocks-proxy.conf;
        proxy_cache_valid 200 15s;
    }
    location = /stocks/cotations {
        limit_req zone=stocks_key burst=50 nodelay;
        include snippets/stocks-proxy.conf;
        proxy_cache_valid 200 5m;
    }
    location = /stocks/fundamental {
        limit_req zone=stocks_key burst=50 nodelay;
        include snippets/stocks-proxy.conf;
        proxy_cache_valid 200 5m;
    }
    location = /stocks/historical {
        limit_req zone=stocks_key burst=50 nodelay;
        include snippets/stocks-proxy.conf;
        proxy_cache_valid 200 1h;
    }
    location = /stocks/fields {
        limit_req zone=stocks_key burst=50 nodelay;
        include snippets/stocks-proxy.conf;
        proxy_cache_valid 200 5m;
    }

    location / { include snippets/stocks-bypass.conf; }   # everything else: pass-through
}
```

`snippets/stocks-bypass.conf`: same proxy headers, `proxy_cache off;`.

**TTL table (authoritative):**

| Location | `proxy_cache_valid 200` | App TTL (`@endpointCache`) | `Cache-Control` sent | Notes |
|---|---|---|---|---|
| `/stocks/historical` | 1h | 1h (`stocksapi_controller.py:84`) | `max-age=300` (`:141`) → ignored | `proxy_ignore_headers` mandatory or nginx caps at 5m |
| `/stocks/fundamental` | 5m | 5m (`:149`) | `max-age=300` (`:211`) | aligned |
| `/stocks/cotations` | 5m | 5m (`:219`) | `max-age=300` (`:267`) | exact match avoids `/live` |
| `/stocks/cotations/live` | 15s | 15s (`:275`) | `max-age=15` (`:312`) | exact match wins |
| `/stocks/fields` | 5m | none | none | recomputed per origin request; 5m staleness accepted (drop to 60s if churn matters) |
| `/stocks/health` | bypass | none | none | liveness |
| `/stocks/mcp` | bypass | n/a | n/a | POST/JSON-RPC mount |

**Why `proxy_ignore_headers Cache-Control` is mandatory:** the app sends `max-age=300` on `/stocks/historical` while its own TTL is 1h; without ignoring the header nginx honors 300s and the 1h rule is defeated. Trade-off: nginx TTL becomes the edge source of truth — keep both TTLs on one review checklist.

**Why these key components:** absent/invalid key → distinct key space, always MISS → hits `verifyAPIKey` (401/429, never cached) → no auth bypass. `X-MCP: true` changes the body (`MCPDetectMiddleware`) but not `$request_uri`, so it must be an explicit key component. `compact=true` already rides in the URI.

**Verify P1:**
```bash
K=sk_test_...; U='http://localhost/stocks/historical?search=PETR4&fields=LUCRO%20LIQUIDO'
curl -sD- -o/dev/null -H "X-API-Key: $K" "$U" | grep -i x-cache-status   # MISS
curl -sD- -o/dev/null -H "X-API-Key: $K" "$U" | grep -i x-cache-status   # HIT
curl -sD- -o/dev/null -H "X-API-Key: BAD" "$U" | grep -iE 'HTTP/|x-cache' # 401 + MISS
```
TODO-14 evidence: `docker stats --no-stream api` before/after `hey -n 5000 -c 50 -H "X-API-Key: $K" "$U"` — origin CPU should stay ≈ idle; capture the `/proc/1/status` ctxt-switch delta to show the GIL path is bypassed.
**Rollback:** delete cached locations / `proxy_cache off` globally; nginx falls back to pass-through with zero app change.

## 1.5 Phase P2 — port scheme, worker containers, keepalive

**Problem (verified):** `config.py:41,53,62` all default `PORT=3200` and `docker-compose.yml:48-50` publishes three host mappings that all default to 3200; in-process `getApp(3200)` collapses all services into one app/thread (`service_manager.py:19-22`). nginx must not assume that forever.

1. Distinct defaults: `USER_PORT=3200`, `STOCKSAPI_PORT=3201`, `ORUNMILA_PORT=3202`, matching compose mappings; existing `.env` values still win; update `.env.example`/README.
2. Worker container behind a compose profile so default `up` is unchanged:
```yaml
  stocksapi:
    build: { context: ., dockerfile: Dockerfile }
    profiles: ["workers"]
    restart: always
    environment:
      - STOCKSAPI_ENABLED=TRUE
      - USER_ENABLED=FALSE
      - ORUNMILA_ENABLED=FALSE
      - SCRAPER_ENABLED=FALSE
      - STOCKSAPI_PORT=3200
      - TZ=America/Sao_Paulo
      # ... mysql env passthrough
    volumes: [ ".:/app", "workspaces:/data/workspaces" ]
```
   `run.py:52` already honors `{SVC}_ENABLED`, so only stocksapi initializes → its own process, own GIL. `upstream stocks_api` then gains `server stocksapi:3200` (and `api:3201`, or drops `api` after cut-over).
3. Keepalive already configured; verify reused connections (`ss -tn state established '( dport = :3200 )'`).

**Verify:** `docker compose --profile workers up -d`; `/stocks/health` served from `stocksapi` (check `X-Forwarded-For` in app log); `docker stats` shows `api` idle, `stocksapi` handling misses.

## 1.6 Phase P3 — remote VPS upstreams + health strategy

```nginx
upstream stocks_api {
    least_conn;
    server api:3200            max_fails=3 fail_timeout=10s;
    server 203.0.113.10:3200   max_fails=3 fail_timeout=10s;  # vps-1
    server 203.0.113.11:3200   max_fails=3 fail_timeout=10s;  # vps-2
    keepalive 32;
}
```
If VPS hostnames rotate, add `resolver 127.0.0.11 valid=10s;` and nginx 1.27 `server name:port resolve;` (document as optional).

Add to `stocks-proxy.conf`:
```nginx
proxy_next_upstream error timeout http_502 http_503 http_504;
proxy_next_upstream_tries 2;
```
Do **not** add `non_idempotent` — a retried POST across nodes can double-execute.

**Active-check gap (OSS nginx has none):**

| Option | Mechanism | Cost | When |
|---|---|---|---|
| Passive (baseline, chosen) | `max_fails=3 fail_timeout=10s`; eject, re-probe at `fail_timeout` | none | P3 default |
| `proxy_next_upstream` | retry next server on error/timeout/502-504 | none; may double-hit origin | add in P3 |
| External prober / OpenResty `lua-resty-healthcheck` | active probes + reload/ejection | ops complexity, new runtime | when a black-hole window >30s is observed (esp. cache-writer death) |
| nginx Plus `health_check` | native active checks | license | only if already bought |
| L4 LB / keepalived+VIP in front of nginx | HA for nginx itself | infra | when the edge becomes HA-required |

`proxy_cache_use_stale ... error timeout` means a dead upstream serves stale cache rather than failing — preferred for read paths.

## 1.7 Phase P4 — handoff design (no code in this plan)

**TODO 13 — drop `{service}_HOST`/`{service}_PORT` without breaking today's switching.** Callers that must keep working: `run.py:52-56` (local-init branch), `run.py:95-98` (`/status`), `main/utils/connectivity.py:45-46`, any peer-URL builder.
1. Add `ROUTING_MODE = legacy | nginx` (default `legacy`) and optional per-service `*_BASE_URL`.
2. One resolver helper: `BASE_URL` if set, else `http://{HOST}:{PORT}` — nothing breaks.
3. Flip `ROUTING_MODE=nginx` per box; `HOST`/`PORT` become bind-only.
4. After all boxes are `nginx` and no caller reads `{svc}_HOST`, delete the fields + `LOCALHOST_ADDRESSES` (`config.py:101`). `run.py` local-init path goes last; `/status` must still report per-service health.
Rollback: set `ROUTING_MODE=legacy` (addresses still present until step 4).

**Redis (TODO 15):** replace cashews `mem://` (`stocksapi_controller.py:17`) with `redis://redis:6379` so the endpoint TTL cache is shared across workers; replace `flock`/`CACHE_LOAD_LOCK` (`cache.py:37,169-183`) with `SET cache_refresh_lock <uuid> NX PX 900000` + owner-token release. **Swarm at 5+:** upstream becomes generated config (compose replicas / consul-template); with >1 nginx, either accept per-node caches or move response cache to a shared tier — decide at 5+, not now.

## 1.8 Quota / rate-limit semantics after caching

| Layer | Counts | Scope | Today | After P1 | Recommendation |
|---|---|---|---|---|---|
| nginx `limit_req` (`stocks_key`) | every request incl. HIT | per key, 300/min + burst 50 | new | uniform ceiling, protects nginx CPU | keep |
| app `verifyAPIKey` quota (`key.py:72-78`) | only MISS | per key, monthly `requestLimit` (10k STARTUP) | all requests | **misses only** | redefine as "origin data requests"; document in pricing |
| app per-minute tier (30 STARTUP) | — | per key | **not implemented** | still not implemented | implement in app/Redis (§3.5b) |
| slowapi `limiter` (`logging_config.py:15`) | per remote IP | global | exists, not on `/stocks` | unchanged | leave; do not key `/stocks` on IP (would 429 whole nginx) |
| Redis counters (P4) | choose | per key + tier | none | accurate 30/300 + monthly | build in P4 |

**Product decision required:** with P1, a STARTUP client can exceed 30/min whenever responses are cached. If the 30/min promise is contractual, enforce it with a key→tier map backed by shared store (nginx keys are unprefixed `token_urlsafe(32)`, `key.py:30` — no tier derivable at nginx) or document that hits are served by the edge.

## 1.9 Anti-scraping note (TODO 17)

The cache key is `(api_key, x-mcp, request_uri)`. Randomizing `/stocks` query params (UUID routing) would make **every request a MISS** and destroy the cache. Randomize at the **page layer** (HTML/JS route consuming `/stocks`), keep the `/stocks` data plane deterministic, and let nginx `limit_req` + app keys absorb direct scraping. TODO-16 (single-tab cookie session) likewise belongs at the page layer, never in the cache path.

## 1.10 Edge cases / risks (implementation)

- **Empty `$http_x_api_key`** → one shared key namespace, but all such requests are 401 (uncached) → all hit origin. Verify `limit_req`'s empty-string bucket does not unfairly 429 anonymous traffic; if it does, give anonymous its own low-rate zone.
- **TTL drift:** nginx TTLs duplicate app decorator TTLs — one review checklist for both.
- **Large `/cotations` bodies** (10y, many tickers): `proxy_max_temp_file_size 512m`, disk `max_size 2g`; watch eviction via `upstream_cache_status`.
- **`proxy_cache_lock` + slow origin:** 20s lock timeout means waiters fall through to origin; watch `urt`.
- **`X-MCP` determinism:** only the exact value `true` mutates the body (`stocksapi_service.py:17`); `X-MCP: TRUE` is a separate non-compacted entry — matches app behavior.
- **Port 3200 collision** is the failure mode of P2 if two roles land on one box — one role per box preferred (§3.2).

---

# Part 2 — Benchmark plan

## 2.0 Grounding: what the code actually does

**0.1 Two independent cache layers — measure them separately.**

| Layer | Implementation | Python in path on HIT? |
|---|---|---|
| nginx response cache | not built yet | **No** — served from disk, uvicorn never contacted |
| app cache `@endpointCache` | `main/app/stocks_api/sync_cache.py:14-32`, cashews `mem://` (`stocksapi_controller.py:17`) | **Yes** |

So "warm hit" is ambiguous: **H1 is split into H1a (nginx HIT) and H1b (app HIT)**.

**0.2 An app-cache HIT still pays two heavy costs.**
- `sync_cache.py:30` — `return asyncio.run(cachedCall())`: **a new event loop is created per request** even on a pure hit; endpoints are sync `def` (`stocksapi_controller.py:85,150,220,276`) so FastAPI runs them in the anyio threadpool (~40 threads) and `asyncio.run()` inside a worker thread is the expensive part.
- Dependency `verifyAPIKey` (`key.py:48-90`) runs on **every** request reaching uvicorn: full-table scan `db.query(StocksAPIKey).all()` (`:57`) + atomic quota `UPDATE` + `commit()` (`:72-78`). The app cache does not skip auth.
Consequence: **nginx** removes Python from the path; the **app** layer only removes pandas query + ORJSON serialization.

**0.3 Quota self-throttle:** `verifyAPIKey` 429s once `currentUsage >= requestLimit` (`key.py:62,80`). Any burst hits this within seconds unless the perf key has a huge `requestLimit` or `KEY_SYSTEM=false`. Scenario prerequisite, not a footnote.

**0.4 Declared vs effective TTL (H5 trap):**

| Endpoint | app TTL | `Cache-Control` | nginx effective if it honors upstream |
|---|---|---|---|
| `/stocks/historical` | 1h (`:84`) | `max-age=300` (`:141`) | **5m**, not 1h |
| `/stocks/fundamental` | 5m (`:149`) | `max-age=300` (`:211`) | 5m |
| `/stocks/cotations` | 5m (`:219`) | `max-age=300` (`:267`) | 5m |
| `/stocks/cotations/live` | 15s (`:275`) | `max-age=15` (`:312`) | 15s |
| `/stocks/fields` | none | none | `proxy_cache_valid` only |

**0.5 GIL measured through one PID:** `service_manager.py:47-51` starts one `threading.Thread` per service port; all uvicorn servers share one process and one GIL (`run.py:46-61`). `/proc/1/status` context-switch counters inside the `api` container aggregate **all** services — that single file is the GIL-contention instrument for H3/S5.

**0.6 TODO 14 is unbuilt:** `/status` (`run.py:77-108`) reports uptime/DBs/services — no latency, no context switches. This benchmark defines the baselines and metric shapes `/status` will later expose (§2.8).

## 2.1 Hypotheses

- **H1a (nginx HIT):** during a 100% nginx-HIT run, uvicorn CPU is independent of RPS (≈ idle); nginx `upstream_requests` counter stays flat. Falsifier: CPU scales with RPS, or upstream requests increment on HIT.
- **H1b (app HIT, nginx bypassed):** app-HIT costs strictly less than app-MISS but **not ≈0** (residual = `asyncio.run()` + `verifyAPIKey` DB scan+write). Falsifier: app-HIT ≈ app-MISS → the app cache adds nothing (a finding).
- **H2:** nginx-HIT RPS at fixed concurrency ≥ **10×** direct-to-uvicorn baseline for the same query, p99 equal or better. Falsifier: <2× → nginx adds a hop without offloading the bottleneck.
- **H3 (the GIL metric):** a non-stocks endpoint probed during a stocks burst shows p99 returning toward its no-load p99 after nginx absorbs the burst. Falsifier: unchanged cross-service p99 → burst was not GIL-bound.
- **H4:** hit ratio ≥ target on a realistic MCP workload (Zipfian ticker popularity; `/stocks/fields` is nginx-only). Falsifier: HIT% below target → key fragmentation dominates.
- **H5:** served body age ≤ effective TTL + margin with `use_stale` + `background_update`; first post-expiry request returns `STALE` + schedules `UPDATING`.

## 2.2 Tooling

**Primary runner — k6 via Docker (`grafana/k6`)**; scripts are JS with `options` + `handleSummary` JSON export.
```bash
# Windows/Docker Desktop: do NOT use --network host (the Linux VM does not share
# the Windows host loopback). Either run k6 as a compose service targeting
# http://nginx:80, or target the host explicitly:
docker run --rm -i -v "%CD%/tests/perf/nginx:/scripts" grafana/k6:latest \
  run --summary-export=/scripts/out/s2_warm.json /scripts/scenarios/s2_warm.js \
  -e BASE_URL=http://host.docker.internal:8080 -e API_KEY=$env:PERF_API_KEY
```
Caveat: PowerShell uses `$env:VAR` / `"%CD%"`, Git-Bash uses `$VAR` / `$(pwd)`. `--network host` silently fails to reach the Windows host — the #1 time-waster on this box.

**Fallbacks:** `hey` (`docker run --rm --network <net> williamyeh/hey -n 20000 -c 50 -H "X-API-Key: $KEY" "http://nginx/stocks/cotations?search=PETR4"`) and `wrk` (`skandyla/wrk -t4 -c50 -d30s --latency`).

**X-Cache-Status distribution:**
```bash
curl -s -o /dev/null -w '%header{x-cache-status}\n' -H "X-API-Key: $K" "$U"   # per request
seq 1 20000 | xargs -P32 -I{} curl -s -o /dev/null -w '%header{x-cache-status}\n' \
  -H "X-API-Key: $PERF_API_KEY" "$U" | sort | uniq -c | sort -rn            # high rate
```
Vocabulary: `HIT, MISS, BYPASS, EXPIRED, STALE, UPDATING, REVALIDATED`. If `STALE`/`UPDATING` never appear, `proxy_cache_use_stale updating` is missing.

**CPU during burst (never idle — 1.68 GB idle is not peak):**
```bash
docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}},{{.MemPerc}}" api nginx
```
Sample ~1/s for the run duration; keep max + mean. `CPUPerc` is % of one core and can exceed 100%.

**Context switches (GIL instrument) — Windows has no pidstat/vmstat, run inside the container:**
```bash
docker exec api sh -c "pidstat -w -p 1 1 30"      # if sysstat present
docker exec api sh -c "vmstat 1 30"                # cs column
# fallback without sysstat: diff /proc/1/status twice
docker exec api sh -c "grep -E 'voluntary|nonvoluntary' /proc/1/status"
```
Caveats: `api` PID 1 aggregates all services (intended for the GIL metric); Docker Desktop counters are VM-visible; `docker stats` granularity ~1s → use ≥30s bursts.

**nginx `stub_status`:** `location = /nginx_status { stub_status; allow 127.0.0.1; deny all; }` → reads `Active connections`, `accepts`, `handled`, `requests`.

**Scenario layout (planned paths, nothing created):**
```
tests/perf/nginx/
  scenarios/  s1_cold.js s2_warm.js s3_rotation.js s4_params.js s5_mixed.js s6_ttl.js s7_gzip.js
  lib/        tickers.js  common.js
  tickers.txt
  collect.sh / collect.ps1 ; run_all.sh / run_all.ps1
  nginx.conf ; README.md
```

## 2.3 Scenarios

All write `out/<scenario>_<mode>_<rep>.json` (+ sampled CSV); `mode` ∈ {`direct`,`nginx`}.

- **S1 cold single query** — purge both caches; one GET through nginx; `MISS`; measure first-fill cost (auth DB, pandas, ORJSON, cache write). Repeat N=200 distinct cold keys for a distribution.
- **S2 warm repeat single query** — fixed query, `vus=50,duration=60s`, nginx cache warm → H1a + H2. Also run the **direct** variant to isolate layer contributions.
- **S3 ticker rotation (fragmentation probe)** — rotate M distinct tickers, same params (each new `search` = new key). Report unique keys, HIT%, RPS(rotation)/RPS(S2); run M ∈ {10,100,500,1000} for the fragmentation curve. This quantifies the known ticker-rotation cache-defeat.
- **S4 parameter variance** — vary `orderBy`, `limit` ∈ {10,100,1000}, `compact` ∈ {false,true}, `dates` on a fixed ticker set → Cartesian blow-up; HIT% vs variant count.
- **S5 mixed concurrent (THE GIL metric)** — parallel: stocks burst (S2/S3 shape) + a constant 5-VU probe against a non-stocks endpoint on the same process (`:8000/status` does DB round trips; and/or USER `/health`). Measure probe p50/p95/p99 during burst vs idle, `api` ctxt-switch rate, `api` CPU. Run `direct` (baseline degradation) and `nginx` (relief); H3 is the delta.
- **S6 TTL expiry / stale-while-revalidate** — warm, idle past the effective TTL, fire one request → expect `STALE` + background `UPDATING`; next → `HIT`; assert body age ≤ TTL+margin against a direct-fetch oracle. Market-hours caveat: outside 10:00–17:30 BRT `/cotations/live` returns the last closing price (`stocksapi_controller.py:310-311`) → assert on `X-Cache-Status` only.
- **S7 gzip on/off** — measure bytes/ratio, TTFB/p95, `api` CPU (must stay flat on HIT), and that `Accept-Encoding` does not split the cache key (`Vary` present via `gzip_vary on`).

## 2.4 Protocol

1. Same box, before/after; identical compose, DB, feather state.
2. Warm-up 30s at ≤10% VUs, discard.
3. 3 repeats; median + min/max; reject a repeat if `cacheAgeHours` (`/stocks/health`, `stocksapi_controller.py:33`) crosses a 12h rebuild boundary.
4. Fixed seeded tickers (`tests/perf/nginx/tickers.txt`); Zipfian for S5/H4, uniform rotation for S3; no unseeded RNG.
5. Pin `PERF_API_KEY` with raised `requestLimit` (or `KEY_SYSTEM=false`); record which mode; `KEY_SYSTEM=true` is the realistic default for H1b/H3.
6. Record B3 session state + run clock for every row.
7. **Cache flush procedure (state must be defined, not assumed):** nginx → `docker exec nginx sh -c "rm -rf /var/cache/nginx/stocks/*"` (or restart if the volume is ephemeral); app cashews → `docker compose restart api` (clears in-process cache AND reloads feather — slow); feather/DB untouched, note `cacheAgeHours`. A HIT% number without its flush provenance is meaningless.
8. Order: `direct` baseline → flush → `nginx` treatment; flush between reps; never interleave unflushed.

## 2.5 Metrics

RPS; p50/p95/p99; error rate (<0.1%); `api` CPU% (burst); `nginx` CPU%; RAM during burst; context switches/s; `X-Cache-Status` mix; upstream requests (counter vs total); cache-key cardinality (MISS count); gzip ratio; staleness age; cold latency. Every row carries `timestamp, mode, flush, cacheAgeHours, marketOpen, KEY_SYSTEM, tickersRef, rep`.

## 2.6 Acceptance thresholds — **ALL PROPOSED, freeze after first real run**

| Hypothesis | Metric | PROPOSED | Rationale |
|---|---|---|---|
| H1a | `api` CPU% during 100% HIT at ≥1000 rps | within +5 pp of idle; upstream_requests flat | HIT must not touch uvicorn |
| H1b | app-HIT vs app-MISS per-request CPU | ≤60% of miss but >5% | residual = asyncio.run + auth DB |
| H2 | S2 RPS vs direct | ≥10×, p99 ≤ baseline, errors <0.1% | removes auth DB + event loop + serialization |
| H3 | S5 probe p99 during burst | ≤ baseline +20% | GIL relief is the whole argument |
| H3 | ctxt-switch rate | ≥30% reduction vs direct | objective GIL proxy |
| H4 | HIT% Zipf workload | ≥70% | realistic MCP repetition |
| H4 | HIT% uniform rotation M≥500 | ≥40% (report actual) | fragmentation is the finding |
| H4 | HIT% pure repeat | ≥95% | sanity ceiling |
| H5 | served body age | ≤ effective TTL + 5s; STALE+UPDATING observed | no stale beyond TTL |
| S3 | RPS(rotation)/RPS(S2) | report; ≥0.4 at M=100 | quantifies fragmentation |
| S6 | STALE-hop p99 vs clean HIT | ≤ +10 ms | stale-while-revalidate near-free |
| S7 | gzip byte reduction | ≥70% JSON; api CPU flat; Vary present, key not split | nginx compresses, not uvicorn |

## 2.7 Results doc layout

```
docs/benchmarks/nginx/
  README.md   PLAN.md   nginx.conf.snapshot
  runs/2026-XX-XX_<commit>/{meta.json, raw/*.json, summary.md}
```
`README.md` summary table: scenario × mode → RPS, p50, p95, p99, api CPU%, cs/s, HIT%, RAM, verdict. Raw naming `<scenario>_<mode>_<rep>.<ext>`, timestamped run dir, never overwrite a previous run.

## 2.8 Feeding `/status` (TODO 14)

This benchmark produces the two baselines `/status` needs:
1. **Per-service p99** — bounded rolling duration histogram per service in a middleware; surface `latency: {p50,p95,p99}`. S5 probe p99 becomes the alert baseline: *"USER p99 during stocks burst ≤ idle p99 + H3 headroom"*.
2. **Context-switch rate** — `/status` reads its own `/proc/self/status` voluntary+nonvoluntary counters, caches last sample + timestamp, reports `ctxSwitchesPerSec`. The direct-vs-nginx delta sets the threshold: *a burst pushing cs/s above the benchmarked nginx ceiling means the burst is leaking past the cache to the GIL*.

## 2.9 Benchmark risks

- Cache key excluding `X-API-Key` would serve one key's response to another and short-circuit usage accounting (`key.py:72-78`) — the plan's §1.4 key includes it; the benchmark must verify tenant isolation explicitly.
- Warm app cache can mask a "cold" S1 → always flush per §2.4.7 and record it.
- `asyncio.run` per request (`sync_cache.py:30`) may dominate the app-HIT cost — H1b is expected to reveal a large residual; that is a finding, not a failed benchmark.
- 12h feather rebuild invalidates app cache mid-run → guard with `cacheAgeHours`.
- Any 429 = aborted run, not a result.
- `.all()` scan (`key.py:57`) grows with the key table → measured auth cost is a lower bound.

---

# Part 3 — Future scaling evolution + risks

## 3.0 Verified ground truth

| Fact | Evidence |
|---|---|
| All three services default to the same port 3200 | `config.py:41,53,62` |
| Services are uvicorn threads in ONE process, shared GIL | `service_manager.py:49-51` |
| Boot selects local-vs-remote by HOST string | `run.py:51-56`; `LOCALHOST_ADDRESSES` `config.py:101` |
| Per-service env gates already exist | `config.py:39,51,60` (`USER_ENABLED`, `STOCKSAPI_ENABLED`, `ORUNMILA_ENABLED`) |
| Single compose `api` service; host ports collide on 3200 | `docker-compose.yml:41-50` |
| Feather cache: 6h mtime staleness, 12h scheduled refresh, per-host `flock` | `cache.py:36,221-227,169-183` |
| No `CACHE_VERSION` constant exists (only `PRESORTED_FLAG_KEY` schema metadata) | `cache.py:38,134`; grep found none in `main/` |
| Endpoint cache is in-process cashews `mem://` | `stocksapi_controller.py:17`, `sync_cache.py:21-27` |
| Rate limiting is in-process slowapi; monthly quota is atomic DB counter | `service_manager.py:24`, `key.py:72-81` |
| Sandbox model has `userId` + `sandboxId`, NO host column | `main/models/sandbox.py:8-11` |
| `FORGEVM_URL` is a single static URL today | `config.py:65` |
| Named constraint: 1 nginx box = single failure domain | accepted now, recorded R1 |

## 3.1 Target topology

**1 box (today + nginx front door):** nginx :80/:443 fronts `/` → `api:8000` and `/stocks/*` → `api:3200`; the single `api` process holds USER/STOCKS_API/ORUNMILA (one GIL) + scraper + db + forgevm + searxng. Cache writer = the one process.

**2 boxes (first extraction — STOCKS_API):**
```
NODE A                                NODE B
nginx :80/443                         api container: STOCKSAPI_ENABLED=TRUE,
  /         -> A:8000                 others FALSE
  /stocks/* -> B:3200 (pinned IP)     STOCKS_API :3200 (own GIL)
api: USER + ORUNMILA :3200            feather writer (Redis lock owner)
db primary, forgevm, searxng
```
Why STOCKS_API first: pure HTTP, self-contained router (`stocksapi_service.py:30-45`), owns the cache scheduler, and moving it removes feather build/load + `rebuildAbbrevs()` (`cache.py:229-246`) GIL contention from USER/ORUNMILA.

**3 boxes (ORUNMILA + ForgeVM split):** A = nginx edge + USER + db primary (+replica warm); B = STOCKS_API + feather writer (Redis lock owner); C = ORUNMILA + forgevm + workspaces volume. Keep ForgeVM co-located with ORUNMILA (sandbox exec is chat-latency-bound; `workspaces` is local, `docker-compose.yml:34,66`). ForgeVM never sits behind the public nginx.

## 3.2 Worker-container extraction

Same image + env gate = a worker with its own GIL; no new Dockerfile.

| Env var | Node A (edge+USER) | Node B (STOCKS_API) | Node C (ORUNMILA) | Notes |
|---|---|---|---|---|
| `USER_ENABLED` | TRUE | FALSE | FALSE | `config.py:39` |
| `STOCKSAPI_ENABLED` | FALSE | TRUE | FALSE | `config.py:51` |
| `ORUNMILA_ENABLED` | FALSE | FALSE | TRUE | `config.py:60` |
| `SCRAPER_ENABLED` | TRUE (writer node only) | FALSE | FALSE | `config.py:77`; exactly ONE scraper fleet-wide |
| `{svc}_HOST` | localhost | localhost | localhost | phase 1 still local-init (`run.py:53`) |
| `{svc}_PORT` | per-role | 3200 | 3200 | one role per box removes the collision entirely |
| `STOCKS_MYSQL_HOST`/`USER_MYSQL_HOST` | db host | db host (remote ok) | db host | `config.py:26,32` |
| `ROUTING_MODE` (new) | legacy→nginx | same | same | §3.4 |

Extraction order + acceptance: **1. STOCKS_API** (`/stocks/health` → `cacheReady:true`; Node A `/status` `run.py:87-99` shows stocks_api local and B reachable; feather built on B). **2. ORUNMILA + ForgeVM** (chat tool round-trip; sandbox created on C). **3. USER last** (most coupled: auth/sessions/JWT; login+me round-trip). **4. SCRAPER**: never two writers (exactly one node logs scraper init).

## 3.3 nginx upstream evolution — validated against the user's plan

**Recommend pinned static upstreams (`BoxIP:publishedPort`) below 5 nodes; Swarm routing mesh at ≥5.** The pinned-address idea is correct now.

```nginx
upstream stocks_api { server 10.0.0.12:3200 max_fails=3 fail_timeout=30s; keepalive 32; }
upstream user_api   { server 10.0.0.10:3200 max_fails=3 fail_timeout=30s; keepalive 32; }
```

| Criterion | Pinned static (chosen) | Swarm mesh (≥5) |
|---|---|---|
| `config.py` URL-switch preserved | Yes — host:port still meaningful | No — becomes VIP/DNS |
| Debuggability | Trivial (`nginx -T`, ping IP) | Overlay + VIP indirection |
| Node add/remove | Manual edit + reload | Automatic reschedule |
| Node failure | `max_fails` ejects; others serve | Mesh re-routes |
| Extra surface | None | Overlay net, gossip, ingress |
| ForgeVM affinity | Easy (pin host) | Mesh breaks affinity |
| Compose-compatible | Yes | Rewrite to stack files |

Price of static upstreams: **no auto-reschedule** (a human edits nginx when a node joins/leaves) — acceptable ≤3 boxes, and it is what keeps today's gradual-extraction path intact. Health: passive + compose healthchecks; promote to OpenResty only if a black-hole window >30s is observed (see §1.6 options table). Add `proxy_connect_timeout 2s; proxy_read_timeout 60s;` and never retry `non_idempotent`.

## 3.4 TODO 13 migration — drop `{service}_HOST`/`{service}_PORT`

End state: the app no longer knows peer addresses; nginx owns routing; services call an internal base URL. Design: `ROUTING_MODE = legacy | nginx` (default `legacy`) + optional `*_BASE_URL`.
- `legacy`: current behavior (`{svc}_HOST`/`{svc}_PORT` + `run.py:53`).
- `nginx`: derive base URLs from `MANSA_INTERNAL_BASE_URL` (e.g. `http://nginx:80`); `HOST`/`PORT` remain bind-only; `run.py:55` `checkServiceConnection` dropped (nginx fails closed); `{svc}_ENABLED` stays as the boot gate in both modes.
Transition: (1) introduce flag default legacy; (2) nginx in front, still legacy; (3) flip per box; (4) delete the properties + `LOCALHOST_ADDRESSES` in a cleanup commit. Rollback: flip back to legacy (addresses still present until step 4).

## 3.5 Redis — exactly two jobs

The endpoint cache stays `mem://` and feather stays local files; Redis does **only**:

**(a) Cross-host rebuild lock.** `flock` (`cache.py:179`) + `CACHE_LOAD_LOCK` (`cache.py:37`) are per-host → two hosts can build concurrently at box #2. Use `SET stocks:cache:rebuild <owner-uuid> NX EX 600`; release only if the value matches (Lua compare-and-del) so a timed-out owner cannot free a successor's lock; acquire before `tryBuildLock` (`cache.py:264-280`) and skip with "another host is building" (current `:268` behavior) if not acquired. Add an explicit `CACHE_VERSION` constant (does not exist today) embedded in feather metadata: readers load only on match, else rebuild; bump = fleet-wide invalidation and the lock guarantees exactly one rebuilder while others serve their stale feather.

**(b) Rate limiting (30/300 rpm tiers, TODO lines 56/67).** Today in-process slowapi = N× quota at N instances; the DB counter (`key.py:72-81`) is monthly calls, already cross-instance correct.

| Approach | Per-key tier | Cross-instance | Verdict |
|---|---|---|---|
| nginx `limit_req` keyed `$http_x_api_key` | needs key→tier map; fixed window; per-nginx zone | No | coarse edge guard only |
| Redis token bucket (Lua) keyed `apiKey` | Yes (30/300 from the key row) | Yes | **recommended authoritative rpm limiter** |
| slowapi in-process | Yes | No | keep off the cross-box path |

Roadmap triggers: add Redis **before box #2** (lock required); add the token bucket with the first multi-instance STOCKS_API. Neither needed on a single box.

## 3.6 Cache strategy across boxes

**Rebuild-on-version per box. Not rsync, not NFS.** Each node builds its own feather from `stocks_db` (deterministic, `cache.py:78-166`), gated by the Redis lock + `CACHE_VERSION`; the lock holder is the writer, others read.
**Staleness exposure (named):** a reader node serves its local feather until its next refresh (`cache.py:254` 6h staleness, `:221-227` 12h scheduler) or a version bump → worst case ~6h stale fundamentals. Live quotes are fetched at source (`stocksapi_controller.py:274`) and unaffected. Accepted.
**Do NOT:** NFS for `/app/cache` (the writer relies on same-FS `os.replace` atomicity `cache.py:163-165` and `flock`; NFS breaks both and adds a SPOF); round-robin over ForgeVM hosts (breaks `/workspace` affinity); a single shared feather file (contention + SPOF). Upgrade path if rebuild cost ever dominates: version-gated rsync push from writer → readers (not now).

## 3.7 Autoscaling story (TODO 11)

Proposed per-role triggers: **STOCKS_API** — `upstream_response_time` p95 >1.5s for 5 min or upstream 5xx >1% (nginx access log + `stub_status`); **ORUNMILA** — in-flight concurrency / sandbox queue depth; **USER** — DB pool saturation (`pool_size=20,max_overflow=40`, `config.py:106-107`), i.e. scale users only after the DB is the bottleneck.
Stays manual (explicitly): nginx upstream entries, MySQL replica promotion, ForgeVM host membership. The only automatic election is the cache-writer (Redis lock). "Autoscale" today = provision a box with the right env matrix + add a pinned upstream; real auto-provisioning is a later OpenResty/consul-template step — do not build it yet.

## 3.8 ForgeVM interplay (TODO 12)

Different plane from the stocks/nginx layer. Add `hostId` (+ optional `forgevmUrl`) to `orunmila_sandboxes` (`main/models/sandbox.py:8-11` has only `userId`+`sandboxId`). **Spawn-time routing:** pick a host once at sandbox creation (`main/app/orunmila/sandbox.py:110`), persist `hostId`, route all later exec/read/write to that host's `forgevm_url` (read from the row instead of static `Config.FORGEVM_URL`, `config.py:65`; tools at `main/app/orunmila/tools.py:106-152`). No per-request round-robin, no live migration. The public nginx fronts stocks/user HTTP only; ForgeVM control plane is app-internal (ORUNMILA → forgevm:7423) and shares only the machine, not the request path.

## 3.9 Risk register

| # | Risk | Impact | Likelihood | Mitigation | Trigger/Owner |
|---|---|---|---|---|---|
| R1 | Single nginx box = SPOF | Total outage | Med (accepted) | Name it; 2nd nginx + keepalived/VIP at box #3 | edge owner |
| R2 | **Quota-on-miss:** nginx HIT bypasses `key.py:72-81` → monthly counter under-counts | Billing/support disputes | High | Decide: edge forwards hit counter, or accept and bill on app-seen calls | product + edge |
| R3 | Stale ≤ TTL (6h fundamentals) on reader nodes | Users see old data | Med | `CACHE_VERSION` + Redis lock; surface `cacheAgeHours` on `/stocks/health` | cache owner |
| R4 | Key fragmentation: `compact`, `X-MCP` rewrite, abbrev, anti-scrape UUIDs mutate the key | Hit-rate collapse | High | Keep `/stocks` keys canonical; sorted normalized args; strip/normalize UUID+tracking params; never let anti-scrape UUIDs enter the cache key | edge + app |
| R5 | Anti-scraping UUID interplay (TODO 17) | Scraping protection silently breaks caching | Med | Design UUID at serializer/response layer; if in path, exempt from `proxy_cache_key` | app |
| R6 | Port collisions: all roles default `:3200` | Boot failure / wrong service | High at 2 roles/box | One role per box; or distinct `{svc}_PORT` | deployer |
| R7 | `flock`/`CACHE_LOAD_LOCK` per-host | Concurrent builds, thrash | High at box #2 | Redis `SET NX EX 600` (§3.5a) | cache owner |
| R8 | In-process slowapi = N× quota | Over-limit traffic at N≥2 | High | Redis token bucket (§3.5b) | edge/app |
| R9 | GIL contention on shared box | One service stalls all | Med | Extract STOCKS_API first; feather load/`rebuildAbbrevs` in-proc | scaling owner |
| R10 | Restarting the cache-writer mid-build | Orphan Redis lock until TTL; deploy races | Med | Never restart the writer while it holds the lock; ownership token + TTL recovers; deploy readers first | ops |
| R11 | `subprocess.run` build blocks the calling daemon thread (`cache.py:271-278`) | Refresh thread stuck | Low | Already isolated in subprocess; Redis lock prevents duplicates | cache owner |
| R12 | Static upstreams: node add = manual edit | Human error / drift | Med | Template upstream file + `nginx -t && nginx -s reload` in the deploy script | ops |
| R13 | `proxy_next_upstream` on POST | Double execution | Med | Exclude `non_idempotent` | edge |
| R14 | MySQL becomes the bottleneck | Latency | Med (later) | Ladder: measure → vertical → read replicas → sharding last | db owner |
| R15 | ForgeVM round-robin temptation | Broken `/workspace` affinity | Med | Host-pair + spawn-time routing only (§3.8) | app |

## 3.10 Migration sequence + verification

| Step | Action | Verify | Pass |
|---|---|---|---|
| 0 | Baseline | `docker compose up -d --build`; `curl -s localhost:8000/status` | `status: healthy`, 3 services |
| 1 | nginx front door (`/`→api:8000, `/stocks/*`→api:3200) | `nginx -T`; `curl -s localhost/stocks/health` | `cacheReady:true` |
| 2 | STOCKS_API worker on Node B (env gate) | `curl -s http://B:3200/stocks/health`; `curl -s A:8000/status` | `stocks_api: local` |
| 3 | Pin upstreams `BoxIP:port` | `nginx -T \| grep -A3 upstream`; GET `/stocks/historical` via nginx | 200 via B |
| 4 | Redis rebuild lock | 2nd `SET ... NX EX 600` returns nil; logs "another host is building" | one builder |
| 5 | `CACHE_VERSION` gate | bump version, restart writer; other node rebuilds once | no duplicate builds |
| 6 | Rate limiting | 31st req/min on a 30-rpm key | 429 |
| 7 | `ROUTING_MODE` flip per box | curl each role through nginx; `/status` healthy | all `nginx` |
| 8 | ForgeVM `hostId` + spawn-time routing | create sandbox → row has `hostId`; exec routes there; kill host → respawn on peer | affinity held |
| 9 | Cleanup: delete `{svc}_HOST/PORT`, `LOCALHOST_ADDRESSES` | `ruff check . && pytest`; no peer-address reads in `run.py` | grep clean |

Every mutation step is followed by `.\ci.ps1` before commit (project rule).

---

# Open decisions (blocking or product-owned)

1. **R2 quota-on-miss** — bill on app-seen calls, or instrument edge cache hits? Blocks enabling `proxy_cache` in production with contractual quotas (§1.8, §3.9 R2).
2. **Per-tier per-minute limit (30 vs 300)** — no nginx-only solution with unprefixed keys (`key.py:30`); decide Redis token bucket vs documented edge behavior (§3.5b).
3. **Active health checks** — stay passive until a writer black-hole >30s is observed, or adopt OpenResty now? (§1.6, §3.3)
4. **Second nginx + VIP** — at which box count does R1 stop being acceptable?
5. **`hostId` on `orunmila_sandboxes`** — confirm the schema migration before any ForgeVM scaling code (§3.8).

# Next actions (not in scope here)

1. Answer the five open decisions.
2. Approve P0/P1 (nginx service + cache locations) — smallest independently deployable step, zero app mutation, instant rollback.
3. Run the benchmark plan against P1 and freeze the PROPOSED thresholds (§2.6) into the results doc.
4. Only then: P2 worker container, P3 remote VPS, P4 routing/Redis refactor.
