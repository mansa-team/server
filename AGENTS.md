## Project Overview
FastAPI-based stock trading/investing platform focused on Brazilian stocks (B3). Multi-service architecture: USER, STOCKS_API, PROMETHEUS (AI chat), SCRAPER.

## Dev Commands
```bash
# Run (Docker)
docker-compose up -d --build   # or `make run`
docker-compose down         # or `make down`

# Lint & Format (required before commit)
ruff check . && ruff format .

# Test
pytest

# Typecheck
mypy

# Coverage report
coverage html
```

## Architecture
- **Layers**: Controller → Service → Model
- **DB**: Two MySQL connections (`engine` for user_db, `stocksEngine` for stocks_db)
- **Entry**: `run.py`, source in `main/`

## Key Quirks
1. **Env vars use weird format**: `GOOGLE_CLIENT.ID`, `STOCKSAPI_KEY.SYSTEM`, `GEMINI_API.KEY` (dots in names)
2. **Ports**: All services map to port 3200 via separate env vars (`USER_PORT`, `STOCKSAPI_PORT`, `PROMETHEUS_PORT`)
3. **Config classes**: Defined in `config.py` — don't guess field names
4. **Migrations**: Alembic in `migrations/`, run via `alembic upgrade head`

## Testing
- Tests in `tests/test_*.py`, use fixtures from `conftest.py`
- Requires MySQL running

## graphify
This project has a graphify knowledge graph at graphify-out/.

Rules:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)