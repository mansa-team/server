# Graph Report - .  (2026-05-05)

## Corpus Check
- Corpus is ~24,056 words - fits in a single context window. You may not need a graph.

## Summary
- 390 nodes · 535 edges · 33 communities (19 shown, 14 thin omitted)
- Extraction: 76% EXTRACTED · 24% INFERRED · 0% AMBIGUOUS · INFERRED: 128 edges (avg confidence: 0.72)
- Token cost: 0 input · 0 output

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
- [[_COMMUNITY_JWT Auth|JWT Auth]]
- [[_COMMUNITY_Entry Point|Entry Point]]
- [[_COMMUNITY_User Sessions|User Sessions]]
- [[_COMMUNITY_Settings|Settings]]
- [[_COMMUNITY_Error Handling|Error Handling]]
- [[_COMMUNITY_Helpers|Helpers]]
- [[_COMMUNITY_Docker|Docker]]

## God Nodes (most connected - your core abstractions)
1. `StocksAPIKey` - 24 edges
2. `User` - 24 edges
3. `UserSession` - 20 edges
4. `TestRoles` - 18 edges
5. `TestUserModel` - 16 edges
6. `TestStocksAPIKeyModel` - 15 edges
7. `FastAPI` - 15 edges
8. `parseUserAgent()` - 14 edges
9. `TestUserSessionModel` - 14 edges
10. `B3Scraper` - 13 edges

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

## Communities (33 total, 14 thin omitted)

### Community 0 - "Stocks API Controller"
Cohesion: 0.07
Nodes (11): verifyAccessToken(), generateKey(), getSessions(), FastAPI, lifespan(), createKey(), generateSecureKey(), getCurrentUser() (+3 more)

### Community 1 - "Authentication Manager"
Cohesion: 0.1
Nodes (17): Authentication System, authenticateUser(), AuthenticationManager, createUserAccount(), getGoogleSSO(), createAccessToken(), hashPassword(), verifyPassword() (+9 more)

### Community 2 - "Stocks Cache & Query"
Cohesion: 0.1
Nodes (6): StocksCacheManager, StocksQueryManager, categorizeColumns(), parseYearInput(), TestCategorizeColumns, TestParseYearInput

### Community 3 - "Session Management"
Cohesion: 0.1
Nodes (7): createSession(), getSessionById(), revokeSession(), SessionManager, validateSession(), UserSession, TestUserSessionModel

### Community 4 - "SQLAlchemy Models"
Cohesion: 0.11
Nodes (6): Base, PrometheusSession, StocksAPIKey, createSession(), TestPrometheusSessionModel, TestStocksAPIKeyModel

### Community 5 - "Roles & Permissions"
Cohesion: 0.08
Nodes (6): IntFlag, TestPermission, TestRoles, UserManager, Permission, Roles

### Community 6 - "Configuration & Logging"
Cohesion: 0.11
Nodes (11): BaseSettings, BaseMansaSettings, Config, DiscordSettings, MysqlSettings, PrometheusSettings, ScraperSettings, StocksApiSettings (+3 more)

### Community 7 - "Scraper B3"
Cohesion: 0.11
Nodes (4): B3Scraper, getInitialData(), runScraper(), ScraperService

### Community 9 - "Device Detection"
Cohesion: 0.19
Nodes (7): detectBrowser(), detectDeviceType(), detectOS(), DeviceInfo, generateFingerprint(), parseUserAgent(), TestDeviceDetection

### Community 10 - "Prometheus Chat"
Cohesion: 0.11
Nodes (19): API Key System, B3 Scraper, Fundamental Data, Gemini Model, Historical Data, Ma'at Stock Algorithm, Mansa Server, MySQL Database (+11 more)

### Community 11 - "User Service"
Cohesion: 0.12
Nodes (5): AuthenticationService, PrometheusService, StocksAPIService, UserService, ServiceManager

### Community 12 - "Scraper Service"
Cohesion: 0.15
Nodes (16): AuthenticationManager, AuthenticationService, PrometheusChatManager, PrometheusGenerator, PrometheusService, SessionManager, UserManager, UserService (+8 more)

### Community 14 - "User Controller"
Cohesion: 0.32
Nodes (3): chat(), createSession(), getHistory()

### Community 16 - "Validators"
Cohesion: 0.7
Nodes (5): Base SQLAlchemy declarative base, PrometheusSession model, StocksAPIKey model, User model, UserSession model

### Community 17 - "Decorators"
Cohesion: 0.83
Nodes (3): getDatabaseUrl(), runMigrationsOffline(), runMigrationsOnline()

### Community 20 - "Prometheus Model"
Cohesion: 0.67
Nodes (3): checkMySqlConnection, MySQL Engine (user_db), MySQL Engine (stocks_db)

## Knowledge Gaps
- **29 isolated node(s):** `Initial migration  Revision ID: 25af7ad931e7 Revises:  Create Date: 2026-04-`, `User sessions table  Revision ID: 4a2f1c9e3b5d Revises: 25af7ad931e7 Create Date`, `Config`, `MySQL Engine (user_db)`, `MySQL Engine (stocks_db)` (+24 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **14 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FastAPI` connect `Stocks API Controller` to `Authentication Manager`, `Stocks Cache & Query`, `Roles & Permissions`, `Prometheus Chat`, `User Service`, `User Controller`?**
  _High betweenness centrality (0.393) - this node is a cross-community bridge._
- **Why does `Config` connect `Configuration & Logging` to `User Service`, `Auth Service`, `Scraper B3`?**
  _High betweenness centrality (0.228) - this node is a cross-community bridge._
- **Why does `ServiceManager` connect `User Service` to `Configuration & Logging`?**
  _High betweenness centrality (0.166) - this node is a cross-community bridge._
- **Are the 15 inferred relationships involving `StocksAPIKey` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`StocksAPIKey` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `User` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`User` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `UserSession` (e.g. with `SessionManager` and `TestUserSessionModel`) actually correct?**
  _`UserSession` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TestRoles` (e.g. with `Permission` and `Roles`) actually correct?**
  _`TestRoles` has 2 INFERRED edges - model-reasoned connections that need verification._