# Graph Report - server  (2026-06-07)

## Corpus Check
- 67 files · ~28,329 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 917 nodes · 1222 edges · 61 communities (46 shown, 15 thin omitted)
- Extraction: 78% EXTRACTED · 22% INFERRED · 0% AMBIGUOUS · INFERRED: 267 edges (avg confidence: 0.69)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `c0260c27`
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

## God Nodes (most connected - your core abstractions)
1. `StocksCacheManager` - 65 edges
2. `StocksQueryManager` - 27 edges
3. `UserSession` - 26 edges
4. `StocksAPIKey` - 24 edges
5. `User` - 24 edges
6. `FastAPI` - 21 edges
7. `TestRoles` - 18 edges
8. `TestUserModel` - 16 edges
9. `Pytest Testing` - 16 edges
10. `TestStocksAPIKeyModel` - 15 edges

## Surprising Connections (you probably didn't know these)
- `PrometheusGenerator` --uses--> `Config`  [INFERRED]
  main/app/prometheus/generation.py → config.py
- `B3Scraper` --uses--> `Config`  [INFERRED]
  main/app/scraper_b3/scraper.py → config.py
- `ScraperService` --uses--> `Config`  [INFERRED]
  main/service/scraper_service.py → config.py
- `DiscordHandler` --uses--> `Config`  [INFERRED]
  main/utils/logging_config.py → config.py
- `TestCacheLRUEviction` --uses--> `StocksCacheManager`  [INFERRED]
  tests/test_cache.py → main/app/stocks_api/cache.py

## Hyperedges (group relationships)
- **Authentication Module** — AuthenticationManager, SessionManager, auth_util, auth_constants, getGoogleSSO [INFERRED]
- **Prometheus AI Chat System** — PrometheusChatManager, PrometheusGenerator, stocksQuery [INFERRED]
- **B3 Stock Data Pipeline** — stocksCache, stocksQuery, verifyAPIKey, B3Scraper [INFERRED]
- **User Management & Sessions** — UserManager, auth_controller, user_controller, SessionManager, auth_util [INFERRED]
- **Configuration & Database Infrastructure** — config_Config, config_engine, config_stocksEngine [INFERRED]
- **User Authentication & Authorization** — user_service, authentication, user_roles, permission_system [INFERRED]

## Communities (61 total, 15 thin omitted)

### Community 0 - "Stocks API Controller"
Cohesion: 0.05
Nodes (35): StocksQueryManager, categorizeColumns(), Tests for lazy JSON deserialization, Tests for lazy JSON deserialization, Query manager should have deserialize method, Query manager should have deserialize method, Integration tests for all query optimizations, Integration tests for all query optimizations (+27 more)

### Community 1 - "Authentication Manager"
Cohesion: 0.07
Nodes (21): Authentication System, authenticateUser(), AuthenticationManager, createUserAccount(), getGoogleSSO(), createAccessToken(), hashPassword(), verifyAccessToken() (+13 more)

### Community 2 - "Stocks Cache & Query"
Cohesion: 0.15
Nodes (10): Tests for connection pool configuration, Tests for connection pool configuration, Stocks engine should have optimized pool settings, Stocks engine should have optimized pool settings, Performance tests for query operations, Performance tests for query operations, Query should respond within 1 second, Query should respond within 1 second (+2 more)

### Community 3 - "Session Management"
Cohesion: 0.09
Nodes (8): createSession(), getSessionById(), revokeSession(), SessionManager, validateSession(), UserSession, TestSessionExpiration, TestUserSessionModel

### Community 4 - "SQLAlchemy Models"
Cohesion: 0.07
Nodes (7): Base, PrometheusSession, StocksAPIKey, User, TestPrometheusSessionModel, TestStocksAPIKeyModel, TestUserModel

### Community 5 - "Roles & Permissions"
Cohesion: 0.06
Nodes (15): BaseSettings, BaseMansaSettings, Config, DiscordSettings, MysqlSettings, PrometheusSettings, ScraperSettings, StocksApiSettings (+7 more)

### Community 6 - "Configuration & Logging"
Cohesion: 0.07
Nodes (7): IntFlag, TestPermission, TestRoles, getCurrentUser(), UserManager, Permission, Roles

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
Cohesion: 0.17
Nodes (7): detectBrowser(), detectDeviceType(), detectOS(), DeviceInfo, generateFingerprint(), parseUserAgent(), TestDeviceDetection

### Community 13 - "Auth Service"
Cohesion: 0.11
Nodes (19): API Key System, B3 Scraper, Fundamental Data, Gemini Model, Historical Data, Ma'at Stock Algorithm, Mansa Server, MySQL Database (+11 more)

### Community 14 - "User Controller"
Cohesion: 0.04
Nodes (44): Bucket A: Security Fixes (quick wins, 30 min), Bucket B: DB Session Cleanup (medium, 1-2 hrs), Bucket C: Testing (medium, 2-3 hrs), Bucket D: Infrastructure (large, 4+ hrs), Category 1: Database Session Management (HIGH), Category 2: Async/Sync Inconsistencies (MEDIUM), Category 3: Security (HIGH), Category 4: Caching & Memory (MEDIUM) (+36 more)

### Community 15 - "Database Utils"
Cohesion: 0.14
Nodes (3): createSession(), PrometheusChatManager, PrometheusGenerator

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
Cohesion: 0.08
Nodes (25): BaseHTTPMiddleware, BaseModel, app(), Tests for standardized error responses (errors.py)., SampleBody, TestErrorResponseModel, TestGenericExceptionHandler, TestHTTPExceptionHandler (+17 more)

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
Cohesion: 0.25
Nodes (7): Architecture, code:bash (# Run (Docker)), Dev Commands, graphify, Key Quirks, Project Overview, Testing

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
Cohesion: 0.24
Nodes (3): FastAPI, Pytest Testing, Tests for pagination utility (utils/pagination.py).

### Community 52 - "Community 52"
Cohesion: 0.25
Nodes (4): lifespan(), checkMySqlConnection(), checkServiceConnection(), runMigrations()

### Community 54 - "Community 54"
Cohesion: 0.32
Nodes (3): chat(), createSession(), getHistory()

### Community 55 - "Community 55"
Cohesion: 0.22
Nodes (3): client(), TestClient with all routers mounted — no lifespan (no DB/service init).      O, TestClient with all routers mounted — no lifespan (no DB/service init).      O

### Community 56 - "Community 56"
Cohesion: 0.22
Nodes (3): generateKey(), createKey(), generateSecureKey()

### Community 59 - "Community 59"
Cohesion: 0.25
Nodes (7): computedHash, skillPath, source, sourceType, skills, backend-code-review, version

### Community 60 - "Community 60"
Cohesion: 0.33
Nodes (5): Tests for optimized search filtering, Tests for optimized search filtering, Filter should use ticker index for O(1) lookup, Filter should use ticker index for O(1) lookup, TestFilterBySearchTerms

## Knowledge Gaps
- **243 isolated node(s):** `version`, `source`, `sourceType`, `skillPath`, `computedHash` (+238 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pytest Testing` connect `Community 50` to `Stocks API Controller`, `Authentication Manager`, `Stocks Cache & Query`, `Session Management`, `SQLAlchemy Models`, `Roles & Permissions`, `Configuration & Logging`, `Scraper Service`, `Community 49`, `Community 55`, `Settings`, `Helpers`?**
  _High betweenness centrality (0.269) - this node is a cross-community bridge._
- **Why does `FastAPI` connect `Community 50` to `Stocks API Controller`, `Authentication Manager`, `Roles & Permissions`, `Configuration & Logging`, `Auth Service`, `Community 51`, `Community 52`, `Community 54`, `Community 56`, `Community 57`, `Community 58`, `Settings`?**
  _High betweenness centrality (0.167) - this node is a cross-community bridge._
- **Why does `StocksQueryManager` connect `Stocks API Controller` to `Stocks Cache & Query`, `Prometheus Chat`, `User Service`, `Responses`, `Enums`, `Prometheus Model`, `MySQL Connectivity`, `Community 60`?**
  _High betweenness centrality (0.069) - this node is a cross-community bridge._
- **Are the 59 inferred relationships involving `StocksCacheManager` (e.g. with `StocksQueryManager` and `TestCacheLRUEviction`) actually correct?**
  _`StocksCacheManager` has 59 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `StocksQueryManager` (e.g. with `StocksCacheManager` and `TestTickerIndex`) actually correct?**
  _`StocksQueryManager` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `UserSession` (e.g. with `SessionManager` and `UserService`) actually correct?**
  _`UserSession` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `StocksAPIKey` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`StocksAPIKey` has 15 INFERRED edges - model-reasoned connections that need verification._