# Graph Report - server  (2026-06-05)

## Corpus Check
- 57 files · ~25,661 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 719 nodes · 957 edges · 49 communities (34 shown, 15 thin omitted)
- Extraction: 77% EXTRACTED · 23% INFERRED · 0% AMBIGUOUS · INFERRED: 223 edges (avg confidence: 0.7)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `ed794283`
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

## God Nodes (most connected - your core abstractions)
1. `StocksCacheManager` - 59 edges
2. `StocksQueryManager` - 27 edges
3. `UserSession` - 26 edges
4. `StocksAPIKey` - 24 edges
5. `User` - 24 edges
6. `TestRoles` - 18 edges
7. `TestUserModel` - 16 edges
8. `TestStocksAPIKeyModel` - 15 edges
9. `FastAPI` - 15 edges
10. `parseUserAgent()` - 14 edges

## Surprising Connections (you probably didn't know these)
- `PrometheusGenerator` --uses--> `Config`  [INFERRED]
  main/app/prometheus/generation.py → config.py
- `B3Scraper` --uses--> `Config`  [INFERRED]
  main/app/scraper_b3/scraper.py → config.py
- `AuthenticationService` --uses--> `Config`  [INFERRED]
  main/service/authentication_service.py → config.py
- `ScraperService` --uses--> `Config`  [INFERRED]
  main/service/scraper_service.py → config.py
- `ServiceManager` --uses--> `Config`  [INFERRED]
  main/utils/service_manager.py → config.py

## Hyperedges (group relationships)
- **Authentication Module** — AuthenticationManager, SessionManager, auth_util, auth_constants, getGoogleSSO [INFERRED]
- **Prometheus AI Chat System** — PrometheusChatManager, PrometheusGenerator, stocksQuery [INFERRED]
- **B3 Stock Data Pipeline** — stocksCache, stocksQuery, verifyAPIKey, B3Scraper [INFERRED]
- **User Management & Sessions** — UserManager, auth_controller, user_controller, SessionManager, auth_util [INFERRED]
- **Configuration & Database Infrastructure** — config_Config, config_engine, config_stocksEngine [INFERRED]
- **User Authentication & Authorization** — user_service, authentication, user_roles, permission_system [INFERRED]

## Communities (49 total, 15 thin omitted)

### Community 0 - "Stocks API Controller"
Cohesion: 0.05
Nodes (26): Pytest Testing, StocksQueryManager, categorizeColumns(), parseYearInput(), Tests for connection pool configuration, Stocks engine should have optimized pool settings, Tests for lazy JSON deserialization, Query manager should have deserialize method (+18 more)

### Community 1 - "Authentication Manager"
Cohesion: 0.08
Nodes (19): Authentication System, authenticateUser(), AuthenticationManager, createUserAccount(), getGoogleSSO(), createAccessToken(), hashPassword(), verifyPassword() (+11 more)

### Community 2 - "Stocks Cache & Query"
Cohesion: 0.06
Nodes (27): Tests for connection pool configuration, Tests for connection pool configuration, Stocks engine should have optimized pool settings, Stocks engine should have optimized pool settings, Tests for lazy JSON deserialization, Tests for lazy JSON deserialization, Query manager should have deserialize method, Query manager should have deserialize method (+19 more)

### Community 3 - "Session Management"
Cohesion: 0.09
Nodes (8): createSession(), getSessionById(), revokeSession(), SessionManager, validateSession(), UserSession, TestSessionExpiration, TestUserSessionModel

### Community 4 - "SQLAlchemy Models"
Cohesion: 0.07
Nodes (8): Base, PrometheusSession, StocksAPIKey, User, createSession(), TestPrometheusSessionModel, TestStocksAPIKeyModel, TestUserModel

### Community 5 - "Roles & Permissions"
Cohesion: 0.1
Nodes (12): BaseSettings, BaseMansaSettings, Config, DiscordSettings, MysqlSettings, PrometheusSettings, ScraperSettings, StocksApiSettings (+4 more)

### Community 6 - "Configuration & Logging"
Cohesion: 0.08
Nodes (6): IntFlag, TestPermission, TestRoles, UserManager, Permission, Roles

### Community 7 - "Scraper B3"
Cohesion: 0.1
Nodes (5): B3Scraper, getInitialData(), calculateInvestingScore(), runScraper(), ScraperService

### Community 8 - "User Model"
Cohesion: 0.06
Nodes (32): Admin Access, API Endpoints, code:bash (curl http://localhost:3200/user/health), code:json ({), code:bash (curl -X DELETE -H "Authorization: Bearer <token>" http://loc), code:json ({), code:bash (curl -X POST -H "Authorization: Bearer <token>" http://local), code:json ({) (+24 more)

### Community 9 - "Device Detection"
Cohesion: 0.08
Nodes (25): API Endpoints, Authentication Management, code:env (#), code:bash (curl http://localhost:3200/auth/health), code:bash (curl -X POST "http://localhost:3200/auth/register" \), code:bash (curl -X POST "http://localhost:3200/auth/login" \), code:bash (curl -X GET "http://localhost:3200/auth/me" \), code:bash (curl -X POST "http://localhost:3200/auth/logout" \) (+17 more)

### Community 10 - "Prometheus Chat"
Cohesion: 0.16
Nodes (8): StocksCacheManager, Tests for dynamic ticker index feature, Ticker index should be built when cache is loaded, Ticker index should contain all tickers from cache, Ticker index should be case-insensitive, Looking up ticker should return valid row index, Ticker index should be rebuilt when cache refreshes, TestTickerIndex

### Community 11 - "User Service"
Cohesion: 0.11
Nodes (13): Performance benchmark tests for stocks API, Performance benchmark tests for stocks API, Ticker index lookup should be O(1) - very fast, Ticker index lookup should be O(1) - very fast, Prefix scan should be much slower than index lookup, Prefix scan should be much slower than index lookup, Index lookup should be significantly faster than scan, Index lookup should be significantly faster than scan (+5 more)

### Community 12 - "Scraper Service"
Cohesion: 0.19
Nodes (7): detectBrowser(), detectDeviceType(), detectOS(), DeviceInfo, generateFingerprint(), parseUserAgent(), TestDeviceDetection

### Community 13 - "Auth Service"
Cohesion: 0.11
Nodes (19): API Key System, B3 Scraper, Fundamental Data, Gemini Model, Historical Data, Ma'at Stock Algorithm, Mansa Server, MySQL Database (+11 more)

### Community 14 - "User Controller"
Cohesion: 0.11
Nodes (5): AuthenticationService, PrometheusService, StocksAPIService, UserService, ServiceManager

### Community 16 - "Validators"
Cohesion: 0.15
Nodes (16): AuthenticationManager, AuthenticationService, PrometheusChatManager, PrometheusGenerator, PrometheusService, SessionManager, UserManager, UserService (+8 more)

### Community 17 - "Decorators"
Cohesion: 0.05
Nodes (14): verifyAccessToken(), chat(), createSession(), getHistory(), generateKey(), getSessions(), FastAPI, lifespan() (+6 more)

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

### Community 30 - "Error Handling"
Cohesion: 0.67
Nodes (3): checkMySqlConnection, MySQL Engine (user_db), MySQL Engine (stocks_db)

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

## Knowledge Gaps
- **186 isolated node(s):** `Initial migration  Revision ID: 25af7ad931e7 Revises: Create Date: 2026-04-0`, `User sessions table  Revision ID: 4a2f1c9e3b5d Revises: 25af7ad931e7 Create Date`, `Add accessTokenHash, operatingSystem, lastActivityAt to user_sessions  Revision`, `Add accessTokenHash, operatingSystem, lastActivityAt, sessionId to user_sessions`, `Remove columns from user_sessions.` (+181 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **15 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Pytest Testing` connect `Stocks API Controller` to `Authentication Manager`, `Stocks Cache & Query`, `Session Management`, `SQLAlchemy Models`, `Roles & Permissions`, `Configuration & Logging`?**
  _High betweenness centrality (0.214) - this node is a cross-community bridge._
- **Why does `FastAPI` connect `Decorators` to `Stocks API Controller`, `Authentication Manager`, `Configuration & Logging`, `Auth Service`, `User Controller`?**
  _High betweenness centrality (0.174) - this node is a cross-community bridge._
- **Why does `StocksQueryManager` connect `Stocks API Controller` to `Stocks Cache & Query`, `Prometheus Chat`, `User Service`, `Decorators`, `Responses`, `Enums`, `Prometheus Model`, `MySQL Connectivity`?**
  _High betweenness centrality (0.096) - this node is a cross-community bridge._
- **Are the 54 inferred relationships involving `StocksCacheManager` (e.g. with `StocksQueryManager` and `TestTickerIndex`) actually correct?**
  _`StocksCacheManager` has 54 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `StocksQueryManager` (e.g. with `StocksCacheManager` and `TestTickerIndex`) actually correct?**
  _`StocksQueryManager` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 21 inferred relationships involving `UserSession` (e.g. with `SessionManager` and `UserService`) actually correct?**
  _`UserSession` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `StocksAPIKey` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`StocksAPIKey` has 15 INFERRED edges - model-reasoned connections that need verification._