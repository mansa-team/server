## Project Overview
FastAPI-based stock trading/investing platform focused on Brazilian stocks (B3). Multi-service architecture: USER, STOCKS_API, ORUNMILA (AI chat), SCRAPER.

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

## Code Style
- Drop the leading underscore from module-level names (`_abbrFrame` → `abbrFrame`).
- Use descriptive variable names; no single- or dual-letter names (the only exception is `df` for DataFrames).

## Testing
- Tests in `tests/test_*.py`, use fixtures from `conftest.py`
- Requires MySQL running


<!-- graft:start -->
## Graft — repo context graph

This repo is indexed in `graft/`: small linked markdown nodes that explain each
system and carry exact file:line spans, kept in sync with the code through git.

For ANY task here — understanding how something works, finding where code lives,
or scoping a change — get context from the graph before grepping or opening
source files. Re-ask freely (it's cheap) and reuse literal identifiers you
already have (symbol, error string, file name) as the query. New to this repo?
Run `graft map` first — a token-budgeted orientation (dir clusters, hubs,
hotspots), no LLM, no key.

- Run `graft ask "<your question>" --source` → ranked nodes with the relevant
  code spans inlined (each hit's ≤8-line crux by default; `--full` for whole
  definitions when the crux isn't enough). Match the tool to the task shape:
  for understanding or editing, the top node IS the answer — cite its
  `covers:` file:line spans and edit straight from `--source`. For
  exhaustive tasks ("every occurrence / every caller of this pattern"), ranked
  results are top-N, not complete — run `graft grep "<literal>"` instead
  (exhaustive over indexed files, grouped by enclosing symbol), falling back
  to raw `grep -rn` only for unindexed files.
- `graft skeleton <file>` → every definition's signature + span, ~10× cheaper
  than reading the file; use it to skim an API surface.
- `graft callers <symbol>` gives precomputed, exact edges — who calls this.
  Add `--direction out` for what it calls, or `--depth N` to walk
  transitively for the full blast radius. For structural questions, skip
  ranking and use this directly.
- Or browse: `graft/INDEX.md` lists every node; follow the links.
- Monorepos and folders of multiple repos rank fairly across sub-projects —
  hits carry `[scope/]` labels naming which one they're from. Narrow with
  `graft ask "<task>" --in <scope>/` once you know where you're working.

If a returned span is truncated ("+N more lines"), open the file at that exact
range before finalizing. Only open source files when a node genuinely lacks a
needed detail, and then at the exact file:line the node points to — never
re-read whole files.

After big code changes, refresh the graph with `graft build` (deterministic,
no API key, $0).
<!-- graft:end -->
