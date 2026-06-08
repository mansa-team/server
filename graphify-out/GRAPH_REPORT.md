# Graph Report - server  (2026-06-08)

## Corpus Check
- 71 files · ~39,184 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1362 nodes · 1963 edges · 124 communities (67 shown, 57 thin omitted)
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 468 edges (avg confidence: 0.65)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `f11197d2`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- [[_COMMUNITY_Stocks API Controller|Stocks API Controller]]
- [[_COMMUNITY_Authentication Manager|Authentication Manager]]
- [[_COMMUNITY_Stocks Cache & Query|Stocks Cache & Query]]
- [[_COMMUNITY_Session Management|Session Management]]
- [[_COMMUNITY_SQLAlchemy Models|SQLAlchemy Models]]
- [[_COMMUNITY_Roles & Permissions|Roles & Permissions]]
- [[_COMMUNITY_Configuration & Logging|Configuration & Logging]]
- [[_COMMUNITY_Scraper B3|Scraper B3]]
- [[_COMMUNITY_User Model|User Model]]
- [[_COMMUNITY_Device Detection|Device Detection]]
- [[_COMMUNITY_Prometheus Chat|Prometheus Chat]]
- [[_COMMUNITY_User Service|User Service]]
- [[_COMMUNITY_Scraper Service|Scraper Service]]
- [[_COMMUNITY_Auth Service|Auth Service]]
- [[_COMMUNITY_User Controller|User Controller]]
- [[_COMMUNITY_Database Utils|Database Utils]]
- [[_COMMUNITY_Validators|Validators]]
- [[_COMMUNITY_Decorators|Decorators]]
- [[_COMMUNITY_Responses|Responses]]
- [[_COMMUNITY_Enums|Enums]]
- [[_COMMUNITY_Prometheus Model|Prometheus Model]]
- [[_COMMUNITY_API Key Model|API Key Model]]
- [[_COMMUNITY_MySQL Connectivity|MySQL Connectivity]]
- [[_COMMUNITY_Auth Constants|Auth Constants]]
- [[_COMMUNITY_SSO|SSO]]
- [[_COMMUNITY_Generator|Generator]]
- [[_COMMUNITY_JWT Auth|JWT Auth]]
- [[_COMMUNITY_Entry Point|Entry Point]]
- [[_COMMUNITY_User Sessions|User Sessions]]
- [[_COMMUNITY_Settings|Settings]]
- [[_COMMUNITY_Error Handling|Error Handling]]
- [[_COMMUNITY_Helpers|Helpers]]
- [[_COMMUNITY_Docker|Docker]]
- [[_COMMUNITY_Community 33|Community 33]]
- [[_COMMUNITY_Community 37|Community 37]]
- [[_COMMUNITY_Community 38|Community 38]]
- [[_COMMUNITY_Community 39|Community 39]]
- [[_COMMUNITY_Community 40|Community 40]]
- [[_COMMUNITY_Community 41|Community 41]]
- [[_COMMUNITY_Community 42|Community 42]]
- [[_COMMUNITY_Community 43|Community 43]]
- [[_COMMUNITY_Community 44|Community 44]]
- [[_COMMUNITY_Community 45|Community 45]]
- [[_COMMUNITY_Community 46|Community 46]]
- [[_COMMUNITY_Community 47|Community 47]]
- [[_COMMUNITY_Community 48|Community 48]]
- [[_COMMUNITY_Community 49|Community 49]]
- [[_COMMUNITY_Community 50|Community 50]]
- [[_COMMUNITY_Community 51|Community 51]]
- [[_COMMUNITY_Community 52|Community 52]]
- [[_COMMUNITY_Community 53|Community 53]]
- [[_COMMUNITY_Community 54|Community 54]]
- [[_COMMUNITY_Community 55|Community 55]]
- [[_COMMUNITY_Community 56|Community 56]]
- [[_COMMUNITY_Community 57|Community 57]]
- [[_COMMUNITY_Community 59|Community 59]]
- [[_COMMUNITY_Community 60|Community 60]]
- [[_COMMUNITY_Community 61|Community 61]]
- [[_COMMUNITY_Community 62|Community 62]]
- [[_COMMUNITY_Community 63|Community 63]]
- [[_COMMUNITY_Community 64|Community 64]]
- [[_COMMUNITY_Community 65|Community 65]]
- [[_COMMUNITY_Community 66|Community 66]]
- [[_COMMUNITY_Community 67|Community 67]]
- [[_COMMUNITY_Community 68|Community 68]]
- [[_COMMUNITY_Community 69|Community 69]]
- [[_COMMUNITY_Community 70|Community 70]]
- [[_COMMUNITY_Community 71|Community 71]]
- [[_COMMUNITY_Community 73|Community 73]]
- [[_COMMUNITY_Community 74|Community 74]]
- [[_COMMUNITY_Community 75|Community 75]]
- [[_COMMUNITY_Community 77|Community 77]]
- [[_COMMUNITY_Community 78|Community 78]]
- [[_COMMUNITY_Community 79|Community 79]]
- [[_COMMUNITY_Community 81|Community 81]]
- [[_COMMUNITY_Community 82|Community 82]]
- [[_COMMUNITY_Community 83|Community 83]]
- [[_COMMUNITY_Community 84|Community 84]]
- [[_COMMUNITY_Community 86|Community 86]]
- [[_COMMUNITY_Community 87|Community 87]]
- [[_COMMUNITY_Community 90|Community 90]]
- [[_COMMUNITY_Community 91|Community 91]]
- [[_COMMUNITY_Community 92|Community 92]]
- [[_COMMUNITY_Community 93|Community 93]]
- [[_COMMUNITY_Community 94|Community 94]]
- [[_COMMUNITY_Community 95|Community 95]]
- [[_COMMUNITY_Community 96|Community 96]]
- [[_COMMUNITY_Community 97|Community 97]]
- [[_COMMUNITY_Community 98|Community 98]]
- [[_COMMUNITY_Community 99|Community 99]]
- [[_COMMUNITY_Community 100|Community 100]]
- [[_COMMUNITY_Community 101|Community 101]]
- [[_COMMUNITY_Community 102|Community 102]]
- [[_COMMUNITY_Community 103|Community 103]]
- [[_COMMUNITY_Community 104|Community 104]]
- [[_COMMUNITY_Community 105|Community 105]]
- [[_COMMUNITY_Community 106|Community 106]]
- [[_COMMUNITY_Community 107|Community 107]]
- [[_COMMUNITY_Community 108|Community 108]]
- [[_COMMUNITY_Community 109|Community 109]]
- [[_COMMUNITY_Community 110|Community 110]]
- [[_COMMUNITY_Community 111|Community 111]]
- [[_COMMUNITY_Community 112|Community 112]]
- [[_COMMUNITY_Community 113|Community 113]]
- [[_COMMUNITY_Community 114|Community 114]]
- [[_COMMUNITY_Community 115|Community 115]]
- [[_COMMUNITY_Community 116|Community 116]]
- [[_COMMUNITY_Community 117|Community 117]]
- [[_COMMUNITY_Community 118|Community 118]]
- [[_COMMUNITY_Community 119|Community 119]]
- [[_COMMUNITY_Community 120|Community 120]]
- [[_COMMUNITY_Community 121|Community 121]]
- [[_COMMUNITY_Community 122|Community 122]]
- [[_COMMUNITY_Community 123|Community 123]]
- [[_COMMUNITY_Community 124|Community 124]]
- [[_COMMUNITY_Community 125|Community 125]]
- [[_COMMUNITY_Community 126|Community 126]]
- [[_COMMUNITY_Community 127|Community 127]]
- [[_COMMUNITY_Community 128|Community 128]]
- [[_COMMUNITY_Community 129|Community 129]]

## God Nodes (most connected - your core abstractions)
1. `StocksCacheManager` - 75 edges
2. `StocksQueryManager` - 39 edges
3. `UserManager` - 39 edges
4. `Roles` - 39 edges
5. `Permission` - 38 edges
6. `_make_stocks_df()` - 27 edges
7. `PrometheusGenerator` - 26 edges
8. `UserSession` - 26 edges
9. `TestQueryFundamental` - 25 edges
10. `StocksAPIKey` - 24 edges

## Surprising Connections (you probably didn't know these)
- `test_cache_scheduler_starts_daemon_thread()` --calls--> `StocksCacheManager`  [INFERRED]
  tests/test_stocks_api_coverage.py → main/app/stocks_api/cache.py
- `app()` --calls--> `register_error_handlers()`  [INFERRED]
  tests/test_error_handlers.py → main/utils/errors.py
- `PrometheusGenerator` --uses--> `Config`  [INFERRED]
  main/app/prometheus/generation.py → config.py
- `B3Scraper` --uses--> `Config`  [INFERRED]
  main/app/scraper_b3/scraper.py → config.py
- `ScraperService` --uses--> `Config`  [INFERRED]
  main/service/scraper_service.py → config.py

## Hyperedges (group relationships)
- **Authentication Module** — AuthenticationManager, SessionManager, auth_util, auth_constants, getGoogleSSO [INFERRED]
- **Prometheus AI Chat System** — PrometheusChatManager, PrometheusGenerator, stocksQuery [INFERRED]
- **B3 Stock Data Pipeline** — stocksCache, stocksQuery, verifyAPIKey, B3Scraper [INFERRED]
- **User Management & Sessions** — UserManager, auth_controller, user_controller, SessionManager, auth_util [INFERRED]
- **Configuration & Database Infrastructure** — config_Config, config_engine, config_stocksEngine [INFERRED]
- **User Authentication & Authorization** — user_service, authentication, user_roles, permission_system [INFERRED]

## Communities (124 total, 57 thin omitted)

### Community 0 - "Stocks API Controller"
Cohesion: 0.1
Nodes (15): Tests for connection pool configuration, Stocks engine should have optimized pool settings, Tests for lazy JSON deserialization, Query manager should have deserialize method, Integration tests for all query optimizations, All optimizations should be implemented, Query filter should use ticker index, Performance tests for query operations (+7 more)

### Community 1 - "Authentication Manager"
Cohesion: 0.06
Nodes (22): Authentication System, authenticateUser(), createUserAccount(), getGoogleSSO(), createAccessToken(), hashPassword(), verifyPassword(), googleCallback() (+14 more)

### Community 2 - "Stocks Cache & Query"
Cohesion: 0.11
Nodes (15): Tests for connection pool configuration, Tests for connection pool configuration, Stocks engine should have optimized pool settings, Stocks engine should have optimized pool settings, Tests for lazy JSON deserialization, Tests for lazy JSON deserialization, Query manager should have deserialize method, Query manager should have deserialize method (+7 more)

### Community 3 - "Session Management"
Cohesion: 0.14
Nodes (3): UserSession, TestSessionExpiration, TestUserSessionModel

### Community 4 - "SQLAlchemy Models"
Cohesion: 0.06
Nodes (8): Base, PrometheusSession, StocksAPIKey, User, createSession(), TestPrometheusSessionModel, TestStocksAPIKeyModel, TestUserModel

### Community 5 - "Roles & Permissions"
Cohesion: 0.06
Nodes (15): BaseSettings, BaseMansaSettings, Config, DiscordSettings, MysqlSettings, PrometheusSettings, ScraperSettings, StocksApiSettings (+7 more)

### Community 7 - "Scraper B3"
Cohesion: 0.1
Nodes (6): B3Scraper, getCurrentSelic(), getInitialData(), calculateInvestingScore(), runScraper(), ScraperService

### Community 8 - "User Model"
Cohesion: 0.06
Nodes (32): Admin Access, API Endpoints, code:bash (curl http://localhost:3200/user/health), code:json ({), code:bash (curl -X DELETE -H "Authorization: Bearer <token>" http://loc), code:json ({), code:bash (curl -X POST -H "Authorization: Bearer <token>" http://local), code:json ({) (+24 more)

### Community 9 - "Device Detection"
Cohesion: 0.08
Nodes (25): API Endpoints, Authentication Management, code:env (#), code:bash (curl http://localhost:3200/auth/health), code:bash (curl -X POST "http://localhost:3200/auth/register" \), code:bash (curl -X POST "http://localhost:3200/auth/login" \), code:bash (curl -X GET "http://localhost:3200/auth/me" \), code:bash (curl -X POST "http://localhost:3200/auth/logout" \) (+17 more)

### Community 10 - "Prometheus Chat"
Cohesion: 0.13
Nodes (9): Get cached stocks data with optional column filtering., StocksCacheManager, Tests for dynamic ticker index feature, Ticker index should be built when cache is loaded, Ticker index should contain all tickers from cache, Ticker index should be case-insensitive, Looking up ticker should return valid row index, Ticker index should be rebuilt when cache refreshes (+1 more)

### Community 11 - "User Service"
Cohesion: 0.09
Nodes (15): Performance benchmark tests for stocks API, Performance benchmark tests for stocks API, Ticker index lookup should be O(1) - very fast, Ticker index lookup should be O(1) - very fast, Prefix scan should be much slower than index lookup, Prefix scan should be much slower than index lookup, Index lookup should be significantly faster than scan, Index lookup should be significantly faster than scan (+7 more)

### Community 12 - "Scraper Service"
Cohesion: 0.1
Nodes (11): detectBrowser(), detectDeviceType(), detectOS(), DeviceInfo, generateFingerprint(), parseUserAgent(), createSession(), getSessionById() (+3 more)

### Community 13 - "Auth Service"
Cohesion: 0.11
Nodes (19): API Key System, B3 Scraper, Fundamental Data, Gemini Model, Historical Data, Ma'at Stock Algorithm, Mansa Server, MySQL Database (+11 more)

### Community 14 - "User Controller"
Cohesion: 0.04
Nodes (44): Bucket A: Security Fixes (quick wins, 30 min), Bucket B: DB Session Cleanup (medium, 1-2 hrs), Bucket C: Testing (medium, 2-3 hrs), Bucket D: Infrastructure (large, 4+ hrs), Category 1: Database Session Management (HIGH), Category 2: Async/Sync Inconsistencies (MEDIUM), Category 3: Security (HIGH), Category 4: Caching & Memory (MEDIUM) (+36 more)

### Community 15 - "Database Utils"
Cohesion: 0.11
Nodes (15): PrometheusGenerator, _make_generator(), Tests to increase coverage for:   - main/app/prometheus/generation.py   - main/a, test_execute_workflow_basic_no_history(), test_execute_workflow_global_request_api_error(), test_execute_workflow_global_request_status_not_200(), test_execute_workflow_global_request_with_api_key(), test_execute_workflow_session_db_exception() (+7 more)

### Community 16 - "Validators"
Cohesion: 0.15
Nodes (16): AuthenticationManager, AuthenticationService, PrometheusChatManager, PrometheusGenerator, PrometheusService, SessionManager, UserManager, UserService (+8 more)

### Community 17 - "Decorators"
Cohesion: 0.28
Nodes (6): extractTokenPayload(), Tests for extractTokenPayload — the standalone token extraction dependency., Create a mock Starlette Request with given headers., Authorization: Bearer (empty) — no token after Bearer., Authorization: Basic xxx — not Bearer, so no token found., TestExtractTokenPayload

### Community 18 - "Responses"
Cohesion: 0.14
Nodes (8): Performance benchmark tests for stocks API, Ticker index lookup should be O(1) - very fast, Prefix scan should be much slower than index lookup, Index lookup should be significantly faster than scan, Query cache should avoid recomputation, Column projection should reduce memory and time, Cache initialization should complete in reasonable time, TestPerformanceBenchmarks

### Community 19 - "Enums"
Cohesion: 0.17
Nodes (7): Tests for dynamic ticker index feature, Ticker index should be built when cache is loaded, Ticker index should contain all tickers from cache, Ticker index should be case-insensitive, Looking up ticker should return valid row index, Ticker index should be rebuilt when cache refreshes, TestTickerIndex

### Community 20 - "Prometheus Model"
Cohesion: 0.17
Nodes (7): Different query parameters should not share cache, Cache should expire after TTL, Tests for query result caching, CacheManager should track cached queries, Query cache should have configurable TTL, getCachedStocks should support column filtering, TestQueryCaching

### Community 21 - "API Key Model"
Cohesion: 0.1
Nodes (19): API Endpoints, API Key Verification, Brazilian Stocks Market API, code:env (#), code:bash (curl http://localhost:3200/stocks/health), code:bash (curl -H "X-API-Key: YOUR_KEY" http://localhost:3200/stocks/k), code:bash (curl "http://localhost:3200/stocks/key/generate?userId=1"), code:bash (curl -H "X-API-Key: YOUR_KEY" "http://localhost:3200/stocks/) (+11 more)

### Community 22 - "MySQL Connectivity"
Cohesion: 0.11
Nodes (13): Different query parameters should not share cache, Different query parameters should not share cache, Cache should expire after TTL, Cache should expire after TTL, Tests for query result caching, Tests for query result caching, CacheManager should track cached queries, CacheManager should track cached queries (+5 more)

### Community 23 - "Auth Constants"
Cohesion: 0.12
Nodes (16): Brazilian Stocks Market Scraper, code:env (#), code:json ({), Configuration Parameters, Constraint Engine ($\Lambda$), Engines, Fundamental Engine ($\Phi$), Global Score Function (+8 more)

### Community 25 - "Generator"
Cohesion: 0.7
Nodes (5): Base SQLAlchemy declarative base, PrometheusSession model, StocksAPIKey model, User model, UserSession model

### Community 26 - "JWT Auth"
Cohesion: 0.83
Nodes (3): getDatabaseUrl(), runMigrationsOffline(), runMigrationsOnline()

### Community 29 - "Settings"
Cohesion: 0.09
Nodes (22): BaseHTTPMiddleware, BaseModel, app(), Tests for standardized error responses (errors.py)., SampleBody, TestErrorResponseModel, TestGenericExceptionHandler, TestHTTPExceptionHandler (+14 more)

### Community 30 - "Error Handling"
Cohesion: 0.67
Nodes (3): checkMySqlConnection, MySQL Engine (user_db), MySQL Engine (stocks_db)

### Community 31 - "Helpers"
Cohesion: 0.06
Nodes (13): Tests for input validation via HTTP endpoints.  Validation is now inline via Bod, PUT /prometheus/sessions/{sessionId} — validates title via Body(...), POST /prometheus/chat — validates text via Body(...), POST /auth/register — validates username, email, password via Body(...), Test that endpoints reject requests with missing required fields., POST /auth/login — validates username, password via Body(...), POST /prometheus/sessions — validates title via Body(...), TestChatValidation (+5 more)

### Community 44 - "Community 44"
Cohesion: 0.22
Nodes (8): API Endpoints, code:env (#), code:bash (python __init__.py), code:mermaid (graph TD), License, Prometheus, Usage, Workflow

### Community 45 - "Community 45"
Cohesion: 0.22
Nodes (8): code:bash (# Build and start), code:env (#), code:bash (curl http://localhost:3200/health), Environment Setup, Health Check, License, Mansa Server, Run with Docker

### Community 46 - "Community 46"
Cohesion: 0.22
Nodes (8): Architecture, CI Pipeline Order, code:bash (# Run (Docker)), Dev Commands, graphify, Key Quirks, Project Overview, Testing

### Community 47 - "Community 47"
Cohesion: 0.29
Nodes (6): DEVELOPER:, PREMIUM:, Prometheus, STOCKS_API, USER:, User structure defined by string roles:

### Community 48 - "Community 48"
Cohesion: 0.33
Nodes (5): downgrade(), Add accessTokenHash, operatingSystem, lastActivityAt to user_sessions  Revision, Add accessTokenHash, operatingSystem, lastActivityAt, sessionId to user_sessions, Remove columns from user_sessions., upgrade()

### Community 49 - "Community 49"
Cohesion: 0.12
Nodes (6): Tests for StocksCacheManager queryCache LRU eviction., Create a StocksCacheManager with a mock DB engine., When columns is None, cache key should be None., TestCacheLRUEviction, TestCacheTTLLogic, TestColumnValidator

### Community 50 - "Community 50"
Cohesion: 0.1
Nodes (24): IntFlag, Covers line 18: GET /stocks/health., Covers line 28: GET /auth/health., Covers line 16: empty password raises ValueError., Covers lines 45-51: verifyAccessToken with expired and invalid tokens., Covers line 67: extractTokenPayload re-raises HTTPException from verifyAccessTok, Covers line 13: UserManager.__init__., Covers lines 139, 141-149: googleLogin endpoint. (+16 more)

### Community 52 - "Community 52"
Cohesion: 0.25
Nodes (4): lifespan(), checkMySqlConnection(), checkServiceConnection(), runMigrations()

### Community 53 - "Community 53"
Cohesion: 0.08
Nodes (13): _make_stocks_df(), Return a small DataFrame with the columns the query module expects., Tests covering query.py lines 142-202., Invalid date -> inner 400 caught by outer except -> 500., search.strip() == '' should still dedup (line 181)., DataFrame without TIME column., Two dates in the range, both valid., Single invalid date -> inner 400 caught by outer except -> 500. (+5 more)

### Community 54 - "Community 54"
Cohesion: 0.32
Nodes (3): chat(), createSession(), getHistory()

### Community 55 - "Community 55"
Cohesion: 0.09
Nodes (18): _make_auth_client(), Covers lines 83-84: session not found., Return (client, app) with auth + user routers and mocked getSession., Covers lines 100-104, 106: GET /user/sessions/current., Covers lines 100-104, 106: session found., Covers line 104: session not found., Covers lines 126-136: DELETE /user/sessions/{sessionId}., Covers lines 126, 131, 135-136. (+10 more)

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (7): Integration tests for all query optimizations, Integration tests for all query optimizations, All optimizations should be implemented, All optimizations should be implemented, Query filter should use ticker index, Query filter should use ticker index, TestQueryOptimization

### Community 57 - "Community 57"
Cohesion: 0.17
Nodes (4): categorizeColumns(), parseYearInput(), TestCategorizeColumns, TestParseYearInput

### Community 59 - "Community 59"
Cohesion: 0.25
Nodes (7): computedHash, skillPath, source, sourceType, skills, backend-code-review, version

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (5): Tests for optimized search filtering, Tests for optimized search filtering, Filter should use ticker index for O(1) lookup, Filter should use ticker index for O(1) lookup, TestFilterBySearchTerms

### Community 63 - "Community 63"
Cohesion: 0.1
Nodes (24): Tests to cover uncovered lines across controllers, UserManager, and auth util., Covers lines 44-54, 63, 66-71: register success, ValueError, generic Exception., Covers lines 87-93, 102: login success and failure paths., Covers lines 107, 109-130, 133: logout token extraction and revocation., test_callback_existing_user(), test_callback_generic_exception(), test_callback_new_user(), test_callback_no_user_info() (+16 more)

### Community 64 - "Community 64"
Cohesion: 0.09
Nodes (22): generateKey(), createKey(), generateSecureKey(), verifyAPIKey(), Tests to increase coverage for query.py, key.py, and cache.py in stocks_api., Tests covering key.py lines 15-40.     Uses asyncio.run() since pytest-asyncio i, Tests covering key.py line 44., Tests covering key.py lines 48-66. (+14 more)

### Community 65 - "Community 65"
Cohesion: 0.22
Nodes (5): verifyAccessToken(), getSessions(), Covers lines 48-49: jwt.ExpiredSignatureError., Covers lines 50-51: jwt.InvalidTokenError., getCurrentUser()

### Community 66 - "Community 66"
Cohesion: 0.08
Nodes (9): Tests covering query.py lines 77-132., Pass field name WITHOUT year (how categorizeColumns returns them)., No historical data columns -> inner 400 caught by outer except -> 500., If an unexpected exception occurs (line 132)., Invalid date format raises exception (line 132)., No historical columns at all -> inner 400 caught by outer except -> 500., Historical query with a year range., Multiple search terms, all found in tickerIndex. (+1 more)

### Community 67 - "Community 67"
Cohesion: 0.1
Nodes (15): _make_prometheus_client(), Covers lines 95-98: DELETE /prometheus/sessions/{sessionId}., Covers lines 95-98: session deleted., Covers lines 96-97: session not found., Return (client, app) with prometheus router and mocked deps., Covers lines 33-36: GET /prometheus/sessions., Covers line 52: POST /prometheus/sessions., Covers lines 62-63, 65-68: PUT /prometheus/sessions/{sessionId}. (+7 more)

### Community 68 - "Community 68"
Cohesion: 0.1
Nodes (4): Exercises the tzinfo-is-None branch (line 144-148)., Exercises the expiresAt-is-None branch (line 143)., Cover all methods in session.py (lines 14-154)., TestSessionManager

### Community 69 - "Community 69"
Cohesion: 0.11
Nodes (14): _make_stocksapi_client(), Covers line 23: GET /stocks/key., Covers line 23: valid API key returns secured=True., Covers line 35: GET /stocks/historical., Covers line 47: GET /stocks/fundamental., Covers lines 52-53, 57-63: GET /stocks/key/generate.      NOTE: stocksapi_contro, Covers lines 52-53: user without GENERATE_API_KEYS permission gets 403., Covers lines 57-60: admin bypasses permission check and generates key. (+6 more)

### Community 71 - "Community 71"
Cohesion: 0.1
Nodes (7): Tests covering query.py lines 22-48., Tests covering cache.py lines 28-76., replaceNan handles direct float NaN values (line 34)., Non-JSON-dict/list string is left as-is., pd.NA is not a string, so lambda returns it unchanged., TestDeserializeJsonColumns, TestStocksCacheManager

### Community 73 - "Community 73"
Cohesion: 0.17
Nodes (8): _make_user_client(), Return (client, app) with user router and mocked deps., Covers line 24: GET /user/me returns currentUser., Covers lines 31-32, 36, 43-44, 48: upgrade developer starter/enterprise., Covers lines 53-54, 56: admin access granted / denied., TestAdminAccess, TestGetMe, TestUpgradeEndpoints

### Community 74 - "Community 74"
Cohesion: 0.14
Nodes (8): client(), pytest_configure(), TestClient with all routers mounted — no lifespan (no DB/service init).      O, TestClient with all routers mounted — no lifespan (no DB/service init).      O, TestClient with all routers mounted — no lifespan (no DB/service init).      O, TestClient with all routers mounted — no lifespan (no DB/service init).      O, TestClient with all routers mounted — no lifespan (no DB/service init).      O, Set required env vars before test collection.      config.py eagerly instantia

### Community 75 - "Community 75"
Cohesion: 0.15
Nodes (7): Covers lines 34, 36-38, 40-44, 46, 48-49, 51, 58-59, 61, 63-67: UserManager.getC, Covers lines 36-38, 40-44, 46, 48-49, 51, 58-59, 61: successful user retrieval., Covers lines 42-44: session validation fails., Covers lines 48-49: user not in DB., Covers lines 65-67: unexpected exception., Covers lines 37-38, 46, 51, 58 (sessionId is None): skips session validation., TestGetCurrentUser

### Community 78 - "Community 78"
Cohesion: 0.25
Nodes (9): AuthenticationManager, SessionManager, PrometheusChatManager, Cover getGoogleSSO (lines 6-14)., Cover __init__ and updateDates (lines 22-37)., Cover executeWorkflow (lines 39-363)., TestPrometheusGeneratorExecuteWorkflow, TestPrometheusGeneratorInit (+1 more)

### Community 79 - "Community 79"
Cohesion: 0.2
Nodes (6): Covers lines 114-115, 117-120, 122, 125: POST /prometheus/chat., Covers lines 111-112: sessionId is None, new session created., Covers lines 114-115, 117-120, 122: existing session with verified ownership., Covers lines 114-115: session ownership check fails., Covers line 125, 126-128: generic Exception in chat., TestPrometheusChat

### Community 81 - "Community 81"
Cohesion: 0.15
Nodes (3): StocksQueryManager, Tests covering query.py lines 50-67., TestFilterBySearchTerms

### Community 82 - "Community 82"
Cohesion: 0.25
Nodes (5): Covers lines 13, 17, 19-20, 22-27: UserManager.addRoleToUser., Covers lines 17, 22-27: user found, role not present, role added., Covers line 27: user already has the role., Covers lines 19-20: user not found raises 404., TestAddRoleToUser

### Community 83 - "Community 83"
Cohesion: 0.7
Nodes (4): Run-Check(), Write-Fail(), Write-Pass(), Write-Step()

### Community 84 - "Community 84"
Cohesion: 0.33
Nodes (5): Tests for optimized search filtering, Filter should use ticker index for O(1) lookup, Tests for optimized search filtering, Filter should use ticker index for O(1) lookup, TestFilterBySearchTerms

### Community 86 - "Community 86"
Cohesion: 0.5
Nodes (3): Covers lines 66, 68-72, 74: GET /user/sessions., Covers lines 66, 68-72, 74: full sessions listing., TestGetSessions

### Community 87 - "Community 87"
Cohesion: 0.5
Nodes (3): Covers lines 143, 145, 147-148: POST /user/sessions/revoke-all., Covers lines 143, 145, 147-148., TestRevokeAllSessions

### Community 129 - "Community 129"
Cohesion: 0.2
Nodes (3): FastAPI, Pytest Testing, Tests for pagination utility (utils/pagination.py).

## Knowledge Gaps
- **396 isolated node(s):** `version`, `source`, `sourceType`, `skillPath`, `computedHash` (+391 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **57 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pytest Testing` connect `Community 129` to `Community 64`, `Authentication Manager`, `Stocks Cache & Query`, `Session Management`, `SQLAlchemy Models`, `Roles & Permissions`, `Configuration & Logging`, `Stocks API Controller`, `Community 74`, `Database Utils`, `Community 49`, `Community 57`, `Helpers`, `Settings`, `Community 63`?**
  _High betweenness centrality (0.334) - this node is a cross-community bridge._
- **Why does `FastAPI` connect `Community 129` to `Community 64`, `Authentication Manager`, `Community 65`, `Roles & Permissions`, `Auth Service`, `Community 50`, `Community 51`, `Community 52`, `Community 54`, `Community 57`, `Community 58`, `Settings`, `Community 63`?**
  _High betweenness centrality (0.135) - this node is a cross-community bridge._
- **Why does `StocksQueryManager` connect `Community 81` to `Community 64`, `Community 129`, `Community 66`, `Stocks Cache & Query`, `Stocks API Controller`, `Community 71`, `Prometheus Chat`, `User Service`, `Responses`, `Enums`, `Prometheus Model`, `Community 53`, `MySQL Connectivity`, `Community 84`, `Community 56`, `Community 60`?**
  _High betweenness centrality (0.057) - this node is a cross-community bridge._
- **Are the 69 inferred relationships involving `StocksCacheManager` (e.g. with `StocksQueryManager` and `TestCacheLRUEviction`) actually correct?**
  _`StocksCacheManager` has 69 INFERRED edges - model-reasoned connections that need verification._
- **Are the 33 inferred relationships involving `StocksQueryManager` (e.g. with `StocksCacheManager` and `TestStocksCacheManager`) actually correct?**
  _`StocksQueryManager` has 33 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `UserManager` (e.g. with `SessionManager` and `Permission`) actually correct?**
  _`UserManager` has 37 INFERRED edges - model-reasoned connections that need verification._
- **Are the 37 inferred relationships involving `Roles` (e.g. with `AuthenticationManager` and `UserManager`) actually correct?**
  _`Roles` has 37 INFERRED edges - model-reasoned connections that need verification._