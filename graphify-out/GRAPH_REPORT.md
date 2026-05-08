# Graph Report - server  (2026-05-08)

## Corpus Check
- 46 files · ~24,474 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 408 nodes · 566 edges · 34 communities (21 shown, 13 thin omitted)
- Extraction: 75% EXTRACTED · 25% INFERRED · 0% AMBIGUOUS · INFERRED: 141 edges (avg confidence: 0.73)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `efa926e3`
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
- [[_COMMUNITY_Entry Point|Entry Point]]
- [[_COMMUNITY_User Sessions|User Sessions]]
- [[_COMMUNITY_Settings|Settings]]
- [[_COMMUNITY_Error Handling|Error Handling]]
- [[_COMMUNITY_Helpers|Helpers]]
- [[_COMMUNITY_Docker|Docker]]
- [[_COMMUNITY_Community 33|Community 33]]

## God Nodes (most connected - your core abstractions)
1. `UserSession` - 26 edges
2. `StocksAPIKey` - 24 edges
3. `User` - 24 edges
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

## Communities (34 total, 13 thin omitted)

### Community 0 - "Stocks API Controller"
Cohesion: 0.07
Nodes (10): verifyAccessToken(), chat(), createSession(), getHistory(), generateKey(), getSessions(), FastAPI, createKey() (+2 more)

### Community 1 - "Authentication Manager"
Cohesion: 0.1
Nodes (12): Authentication System, authenticateUser(), AuthenticationManager, createUserAccount(), createAccessToken(), hashPassword(), verifyPassword(), Google OAuth (+4 more)

### Community 2 - "Stocks Cache & Query"
Cohesion: 0.1
Nodes (4): UserSession, Pytest Testing, TestSessionExpiration, TestUserSessionModel

### Community 3 - "Session Management"
Cohesion: 0.1
Nodes (6): StocksCacheManager, StocksQueryManager, categorizeColumns(), parseYearInput(), TestCategorizeColumns, TestParseYearInput

### Community 4 - "SQLAlchemy Models"
Cohesion: 0.08
Nodes (6): IntFlag, TestPermission, TestRoles, UserManager, Permission, Roles

### Community 5 - "Roles & Permissions"
Cohesion: 0.11
Nodes (6): Base, PrometheusSession, StocksAPIKey, createSession(), TestPrometheusSessionModel, TestStocksAPIKeyModel

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
Cohesion: 0.11
Nodes (5): AuthenticationService, PrometheusService, StocksAPIService, UserService, ServiceManager

### Community 12 - "Scraper Service"
Cohesion: 0.15
Nodes (16): AuthenticationManager, AuthenticationService, PrometheusChatManager, PrometheusGenerator, PrometheusService, SessionManager, UserManager, UserService (+8 more)

### Community 14 - "User Controller"
Cohesion: 0.2
Nodes (5): createSession(), getSessionById(), revokeSession(), SessionManager, validateSession()

### Community 15 - "Database Utils"
Cohesion: 0.31
Nodes (7): getGoogleSSO(), googleCallback(), googleLogin(), isSecureScheme(), login(), logout(), register()

### Community 16 - "Validators"
Cohesion: 0.4
Nodes (4): lifespan(), checkMySqlConnection(), checkServiceConnection(), runMigrations()

### Community 17 - "Decorators"
Cohesion: 0.7
Nodes (5): Base SQLAlchemy declarative base, PrometheusSession model, StocksAPIKey model, User model, UserSession model

### Community 18 - "Responses"
Cohesion: 0.83
Nodes (3): getDatabaseUrl(), runMigrationsOffline(), runMigrationsOnline()

### Community 21 - "API Key Model"
Cohesion: 0.67
Nodes (3): checkMySqlConnection, MySQL Engine (user_db), MySQL Engine (stocks_db)

## Knowledge Gaps
- **29 isolated node(s):** `Initial migration  Revision ID: 25af7ad931e7 Revises:  Create Date: 2026-04-`, `User sessions table  Revision ID: 4a2f1c9e3b5d Revises: 25af7ad931e7 Create Date`, `Config`, `MySQL Engine (user_db)`, `MySQL Engine (stocks_db)` (+24 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **13 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FastAPI` connect `Stocks API Controller` to `Authentication Manager`, `Session Management`, `SQLAlchemy Models`, `Prometheus Chat`, `User Service`, `Database Utils`?**
  _High betweenness centrality (0.378) - this node is a cross-community bridge._
- **Why does `Config` connect `Configuration & Logging` to `User Service`, `Auth Service`, `Scraper B3`?**
  _High betweenness centrality (0.211) - this node is a cross-community bridge._
- **Why does `ServiceManager` connect `User Service` to `Configuration & Logging`?**
  _High betweenness centrality (0.201) - this node is a cross-community bridge._
- **Are the 21 inferred relationships involving `UserSession` (e.g. with `SessionManager` and `UserService`) actually correct?**
  _`UserSession` has 21 INFERRED edges - model-reasoned connections that need verification._
- **Are the 15 inferred relationships involving `StocksAPIKey` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`StocksAPIKey` has 15 INFERRED edges - model-reasoned connections that need verification._
- **Are the 16 inferred relationships involving `User` (e.g. with `TestUserModel` and `TestStocksAPIKeyModel`) actually correct?**
  _`User` has 16 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `TestRoles` (e.g. with `Permission` and `Roles`) actually correct?**
  _`TestRoles` has 2 INFERRED edges - model-reasoned connections that need verification._