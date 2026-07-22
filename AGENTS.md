## Project Overview
FastAPI-based stock trading/investing platform focused on Brazilian stocks (B3). Multi-service architecture: USER, STOCKS_API, PROMETHEUS (AI chat), SCRAPER.

## Dev Commands
```bash
# Run (Docker)
docker-compose up -d --build   # or `make run`
docker-compose down         # or `make down`

# Local CI (run before committing — mirrors .github/workflows/ci.yml)
.\ci.ps1              # all checks: lint, format, mypy, tests+coverage, bandit
.\ci.ps1 -Lint        # lint + format only
.\ci.ps1 -Test        # tests + coverage only
.\ci.ps1 -Fast        # skip mypy + bandit (quick check)
.\ci.ps1 -Typecheck   # mypy only
.\ci.ps1 -Security    # bandit only

# Lint & Format (required before commit)
ruff check . && ruff format .

# Test
pytest

# Typecheck
mypy

# Coverage report
coverage html
```

### CI Pipeline Order
Always run `.\ci.ps1` before pushing. It runs these checks in order:
1. **Ruff Lint** — `ruff check main/ tests/`
2. **Ruff Format** — `ruff format --check .`
3. **mypy Typecheck** — `mypy main/`
4. **Tests + Coverage** — `pytest --cov=main --cov-report=term-missing --cov-report=xml -q`
5. **Coverage Threshold** — must be ≥ 80%
6. **Bandit Security** — non-blocking (advisory only)

Exit code: 0 = all passed, 1 = at least one failed. Bandit failures are non-blocking.

## Architecture
- **Layers**: Controller → Service → Model
- **DB**: Two MySQL connections (`engine` for user_db, `stocksEngine` for stocks_db)
- **Entry**: `run.py`, source in `main/`

## Stocks API — Pandas-First Pattern
- **Cache**: `StocksCacheManager` loads `SELECT * FROM b3_stocks` into DataFrame at startup, 12h refresh
- **Query**: `StocksQueryManager` does in-memory filtering, O(1) tickerIndex lookup
- **Compression**: 6-layer field abbreviation, number suffixing, columnar format
- **Auth**: API keys via `X-API-Key` header, SHA-256 hashed, atomic quota enforcement
- **Key files**: `main/app/stocks_api/cache.py`, `query.py`, `compressor.py`, `key.py`

## Scraper B3 (Xango) — Batch Data Pipeline
- **Schedule**: APScheduler cron, configurable via `SCRAPER_SCHEDULER` env var
- **Sources**: statusinvest, tradingview, investidor10, oceans14, bcb.gov.br, Google News RSS
- **Scoring**: Xango score (growth, volatility, consistency, max drawdown, liquidity, ON penalty)
- **Key files**: `main/app/scraper_b3/scraper.py`, `xango.py`

## Auth/Users — Dual-Layer Session Security
- **Session**: JWT (sessionId) + DB liveness check (UserSession table)
- **RBAC**: IntFlag bitmask (USER, PREMIUM, DEVELOPER_STARTER, DEVELOPER_ENTERPRISE, ADMIN)
- **SSO**: Google OAuth2 via fastapi_sso
- **Key files**: `main/app/authentication/session.py`, `util.py`, `user/user.py`

## Key Quirks
1. **Env vars use weird format**: `GOOGLE_CLIENT.ID`, `STOCKSAPI_KEY.SYSTEM`, `GEMINI_API.KEY` (dots in names)
2. **Ports**: All services map to port 3200 via separate env vars (`USER_PORT`, `STOCKSAPI_PORT`, `PROMETHEUS_PORT`)
3. **Config classes**: Defined in `config.py` — don't guess field names
4. **Migrations**: Alembic in `migrations/`, run via `alembic upgrade head`

## Testing
- Tests in `tests/test_*.py`, use fixtures from `conftest.py`
- Requires MySQL running

## Prometheus (AI Chat) — Strengths & Gaps

### What It Does Well
- **Memory system**: 7-layer architecture (DB schema, system prompt injection, search tool, extraction, maintenance)
- **Tool calling**: 8 registered tools (memory, state, file ops, code execution) + MCP integration (stocks, searxng)
- **Streaming**: SSE-based response streaming with real-time token delivery
- **Session management**: Persistent chat history with JSON storage
- **Episode summarization**: Auto-summarizes long conversations using Gemini

### What It Should Be Doing (Gaps)
- **GenAI native tool calling**: Currently uses custom dispatch loop, should migrate to Gemini's native function calling
- **Code execution sandbox**: ForgeVM — async sandboxed Python execution with per-user workspaces, file sync, auto-recreation on death, TTL-based lifecycle
- **Redis caching**: No caching layer for frequent queries
- **CORS validation**: Missing for Prometheus endpoints

### Pandas-First Approach (80%+ Rule)
- **Stocks API** exemplifies this pattern: `StocksCacheManager` loads `SELECT * FROM b3_stocks` into pandas DataFrame at startup
- **Benefits**: In-memory filtering, O(1) ticker lookup via index, no repeated DB queries
- **Trade-off**: Initial load time (1.6s for 652 stocks) vs zero-latency queries afterward
- **Applies to**: Any read-heavy endpoint with <10k rows that fits in memory

### Memory Keys
- `preference` — user investment style, risk tolerance, favorite tickers
- `analysis` — past analysis results, portfolio performance
- `feedback` — user reactions, quality ratings
- `context` — conversational state, recent topics

## graphify
This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)