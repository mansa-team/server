# PONYTAIL.md — proposed cuts, NOT applied. Approve before any edit.

Status: PROPOSAL. Nothing below is cut. Reply approve (all / by line) or reject.
Format: `<tag> <what>. <replacement>. [path]`. Ranked biggest cut first.

## Proposed (awaiting approval)

delete Merge test_prometheus_auth_coverage.py into resume/streammessage/controller/session tests; keep one file per area. [tests/test_prometheus_auth_coverage.py] (~450)
shrink Replace make_*_client helpers + per-test FastAPI builds with conftest fixtures. [tests/test_controllers_coverage.py] (~250)
shrink Collapse 5x make_manager/make_stocks_df helpers + overlapping query cases into shared helpers + parametrized cases. [tests/test_stocks_api_coverage.py] (~250)
shrink Parametrize single-assert guard classes into tables. [tests/test_stocks_compress.py] (~150)
delete Delete test_stocks_util.py; identical cases live in test_stocks_api_util_coverage.py. [tests/test_stocks_util.py] (~99)
stdlib Delete test_pagination.py dummy /items app; re-tests FastAPI validation, not app code. [tests/test_pagination.py] (~85)
shrink Extract repeated quota-update statement into one helper; 7 tests copy it. [tests/test_api_key_quota_atomic.py] (~80)
delete Delete TestMemoryToolFunctions/TestToolRegistry dupes; identical asserts in test_prometheus_tools.py. [tests/test_memory_tools_wiring.py] (~75)
shrink Parametrize decay-formula cases into one table. [tests/test_relevance_score.py] (~60)
shrink Parametrize one-liner mock chains via shared mockDb factory + tables. [tests/test_compact.py] (~55)
delete Merge TestConcurrentGetSession into TestGetSession; delete test_http_session_coverage.py. [tests/test_http_session_coverage.py] (~50)
shrink Triple appendHistory try/except; extract _persistEvent(db, sessionId, entry). [main/app/prometheus/agent.py] (~35)
stdlib logging.handlers QueueHandler/QueueListener replaces hand deque+Lock+Event+thread queue. [main/utils/logging_config.py] (~25)
shrink Move duplicated mock_forgevm() into conftest.py. [tests/test_sandbox.py] (~20)
delete Dual lru_cache getAbbr/getNest + rebuildAbbrevs + function-local import; compute inline. [main/app/stocks_api/compress.py] (~18)
stdlib Delete TestEbbinghausRetention; asserts math.exp() not app behavior. [tests/test_memory_maintenance.py] (~15)
delete CACHE_NESTED_PATH/sampleParts/sampleCols/nestedSample plumbing; sample the loaded frame. [main/app/stocks_api/cache.py] (~15)
shrink Duplicate existing/similar update blocks in upsertMemory; extract _touch helper. [main/app/prometheus/memory.py] (~14)
delete Lossy SUF suffixes + DF/DI year-stripping in compactValue; keep float rounding. [main/app/stocks_api/compress.py] (~14)
yagni Delete inspect.getsource text-scan test; asserts source absence not behavior. [tests/test_agent_sandbox_integration.py] (~13)
delete getHistoricalFields/getFundamentalColumns/invalidateFieldData; zero callers. [main/app/prometheus/compact.py] (~12)
shrink scoreRecency/scoreCandidates identical dict shape; extract _scoreRow. [main/app/prometheus/memory.py] (~12)
native Coverage-threshold inline XML parse; use coverage report --fail-under=80. [ci.ps1] (~12)
yagni StocksQueryManager single-instance class + snapshot() fallback; module functions suffice. [main/app/stocks_api/query.py] (~12)
delete getDeviceName + device/browser/os keys; createSession never populates them, always None. [main/app/authentication/session.py] (~11)
delete try/except ImportError fallback + comment block; raw import per project rule. [main/models/user.py:20-29] (~10)
yagni matrixKey/matrixUserTag single-use helpers; inline f-strings. [main/app/prometheus/memory.py] (~10, verify — may be gone post-P1)
stdlib parseDate/parseDateRange calendar logic; datetime.date.fromisoformat covers it. [main/app/stocks_api/util.py] (~10)
shrink Hand-rolled mypy capture block; use existing Run-Check. [ci.ps1] (~10)
shrink isSecureScheme try/except+split into one expression. [main/controller/authentication_controller.py] (~7)
shrink Logout token block; call extractTokenPayload. [main/controller/authentication_controller.py] (~7)
shrink Auto-fix triple ruff invocation; single ruff check --fix. [ci.ps1] (~8)
shrink loadFieldData isinstance branching; one-liner coercions. [main/app/prometheus/compact.py] (~8)
shrink Migrator chdir dance; pass cwd= to subprocess.run. [main/utils/migrator.py] (~6)
yagni FALLBACK_METRIC_RE + extractMetrics useRegistry param; sole caller passes True. [main/app/prometheus/compact.py] (~6)
delete forgevm.yaml defaults: block; app passes all four explicitly. [forgevm.yaml] (~6)
shrink initialize/reconnect duplicate steps; extract _connect. [main/app/prometheus/mcp.py] (~6)
stdlib orjson→json fallback + sniffing in deserializeJsonColumns; orjson-only. [main/app/stocks_api/query.py] (~6)
shrink buildTickerIndex loop + sortCacheFrame try/except; dict comprehension + single sort_values. [main/app/stocks_api/cache.py] (~6)
shrink createAccessToken tuple return; all callers discard 2nd element. [main/app/authentication/util.py] (~5)
delete decodeEmbeddings non-bytes branch; sole caller passes bytes only. [main/app/prometheus/vector.py] (~5)
delete exceptSessionId param + branch in revokeAllSessions; sole caller passes None. [main/app/authentication/session.py] (~4)
shrink checkServiceConnection double-except; collapse to one. [main/utils/connectivity.py] (~4)
shrink getMatrix redundant asyncio.run get after set; return fresh values. [main/app/prometheus/memory.py] (~4)
shrink countTokensCached one-line wrapper; inline. [main/app/prometheus/memory.py] (~4)
delete stocks-cache:/app/cache mount + volumes entry; .:/app bind covers it. [docker-compose.yml] (~3)
delete Unused StocksApiSettings KEY/DEFAULT_QUOTA/QUOTA_RESETDAYS fields. [config.py] (~3) - soon to be implemented, keep the KEY and consider removing the DEFAULT_QUOTA/QUOTA_RESETDAYS
delete includeInactive param + branch in getUserSessions; never True. [main/app/authentication/session.py] (~3)
shrink queryHistorical/queryFundamental/queryCotations triple blocks; one validateFields + envelope helper. [main/app/stocks_api/query.py] (~30)
delete TestSessionExpiryConfig; covered by TestSessionExpiration in test_sessions.py. [tests/test_auth_util.py] (~30)
delete --mount=type=cache paired with --no-cache-dir; keep one mechanism. [Dockerfile] (~2)
delete Unused import asyncio. [run.py] (~1)
delete mcp==1.29.0 pin; zero direct imports, transitive-only. [requirements.txt] (~1)

Net proposed: ~2,200 lines + 1 dependency (mcp pin).

## Disputed (already litigated — needs your ruling to proceed)

shrink toColumnar/walk/fixHeaders generic h/d pipe-encoding; keep compactCotations nested h/d for cotation series (Alt C: gzip saves transport bytes, pipe-encoding saves LLM tokens — orthogonal). [main/app/stocks_api/compress.py] (~40)
delete sync_cache.py wrapper; use cashews @cache directly. [main/app/stocks_api/sync_cache.py] (~31) — you blessed shrink-only. (keep the decorator, refused or find a way to make @caceh async, dont create helper functions to make it work properly, the @cache should go above the controller func, not a different func at this case)
delete subprocess.run self-spawn + fcntl lock; direct build in thread. [main/app/stocks_api/cache.py] (~28) — restored deliberately (OOM risk). (building in the thread wouldnt stall the entire operation and also, if im running more than one instance of the server, they could clash or idk)
delete SandboxManager.write_bytes. [main/app/prometheus/sandbox.py] (~10) — restored, 3 workspace tests call it. (delete it, keep only write_file)
delete toVectorString/fromVectorString converters. [main/app/prometheus/vector.py] (~14) — kept for MySQL 9 compat read path. (consider making a plan to upgrade the mysql version in the container to 9 then afterwards, so we can properly replace it. keep for the last, after every change has been implemenmted)

## Held out (your ignore rules — not proposed)

shrink 10 repetitive try/except-nan blocks into one safe() helper. [main/app/scraper_b3/scraper.py] (~35) — scraper.py ignored.
delete historicalCotationProfits_Oceans14 + task slot. [main/app/scraper_b3/scraper.py] (~13) — scraper.py ignored.
shrink tagAlong triple-fallback regex into single pattern. [main/app/scraper_b3/scraper.py] (~6) — scraper.py ignored.

## Refused

delete Abbreviation engine autoAbbreviate/dedupAbbrev/generateAbbreviations/detectNestedFields; return full names, gzip covers size. [main/app/stocks_api/util.py] (~55) - the abbreviations serve the porpouse of compressing token outputs for ai agents that use the MCP for the stocks api
delete Manual pa.schema build + arrowTypeFor; pa.Table.from_pandas infers types. [main/app/stocks_api/cache.py] (~20) - possible negative performance outcomes
shrink search_memory/save_memory duplicate SessionLocal blocks; extract _withDb. [main/app/prometheus/tools.py] (~10) - bloated simplification
delete SessionManager.updateLastActive; zero callers. [main/app/authentication/session.py] (~8) - the api/frontend should log when a user is active and update this param so the /sessions track the current situation of user sessions
delete Manual Docker Compose curl-install; runners ship docker compose. [.github/workflows/ci.yml] (~5) - working well enough, dont change
shrink Single-entry strategy.matrix; hardcode python-version. [.github/workflows/ci.yml] (~4) - working well enough, dont change
shrink Two pip install steps in builder; merge into one. [Dockerfile] (~3) - working well enough, dont change
delete Duplicate Show API logs step; container-logs step covers it. [.github/workflows/ci.yml] (~3) - working well enough, dont change
delete DEVELOPER_STARTER/DEVELOPER_ENTERPRISE aliases; both equal USER, never assigned. [main/utils/roles.py] (~3) - keep, going to be implemented soon
delete Heredoc docker-compose.ci.yml; reuse root compose with env overrides. [.github/workflows/ci.yml] (~28) - working well enough, dont change
shrink Triple-3200 api port mappings; distinct defaults or one mapping. [docker-compose.yml] (~2) - working well enough, dont change