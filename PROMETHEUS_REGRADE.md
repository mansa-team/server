# Prometheus Regrade — Full Code Review

> **Date:** 2026-07-20
> **Scope:** All Prometheus subsystems including memory, summarizer, loop events, sandbox, frontend
> **Previous Grade:** C+ (incomplete memory system, no episode summarization, no loop event persistence)
> **New Grade:** B+ (significant improvements across all subsystems)

---

## Grade Summary

| Subsystem | Grade | Change | Notes |
|-----------|-------|--------|-------|
| Memory System | B+ | ↑ from D | Vector embeddings + FULLTEXT fallback, Jaccard dedup |
| Summarizer/Episodes | B | ↑ from F | Token-based episodes, Gemini merge, smart truncation |
| Loop Events | A- | ↑ from N/A | Clean persistence, frontend integration, observation masking |
| Core Architecture | B+ | ↑ from C | Clean layering, but agent.py too large |
| Security | B+ | ↑ from B | Parameterized SQL, sandbox path validation, rate limiting |
| Performance | B | ↑ from C- | Episode summarization reduces tokens ~43%, but no embedding cache |
| Code Quality | B | ↑ from C | Type hints, docstrings, but large files and dead code |
| **Overall** | **B+** | **↑ from C+** | **Major improvement, production-ready with caveats** |

---

## 1. Memory System (B+)

### What's Good
- **Vector embeddings** (384-dim sentence-transformers) with cosine similarity search via numpy
- **MySQL FULLTEXT fallback** when numpy unavailable (Docker environments)
- **Jaccard similarity** (`findSimilarKey`) for key dedup/merging — prevents duplicate memories
- **Content hash dedup** (MD5) to prevent storing identical content twice
- **Role-based limits** (50 basic / 250 extended users) with automatic pruning of oldest low-score memories
- **Soft delete** via `archivedAt` timestamp
- **Per-tool SessionLocal** with `try/finally` cleanup — no connection leaks
- **Upsert pattern** — updates existing memory if key matches, boosts `accessCount`

### Bugs Found
- **`memory.py:168` column mismatch**: `deleteMemory()` filters by `PrometheusMemory.archivedAt` but the model defines `archivedAt` as a column. However, line 168 says `PrometheusMemory.deleted_at` — this will fail at runtime.
- **`upsertMemory()` double embed**: calls `embed()` twice for the same content (once for similar key check, once for storage) — wasteful
- **`memory.py:search()` two DB sessions**: opens separate sessions for vector search and FULLTEXT — could be one

### Recommendations
1. Fix the `archivedAt` vs `deleted_at` column mismatch in `deleteMemory()`
2. Cache the embedding result in `upsertMemory()` to avoid double computation
3. Consider adding an embedding cache (LRU) for the sentence-transformers model

---

## 2. Summarizer/Episodes (B)

### What's Good
- **Token-based episode creation** with configurable budget (`EPISODE_TOKEN_BUDGET = 8000`)
- **Episode consolidation** via Gemini merge with structured JSON output (`MERGE_SCHEMA`)
- **Smart truncation** with tag-aware cutting (preserves XML tags at 500 chars)
- **Episode cap** (`EPISODE_CAP = 12`) with automatic merge when exceeded
- **Fallback tokenizer** — `len(text) // 3` when `genai.LocalTokenizer` unavailable
- **`dedent_multiline()`** removes indentation before sending to Gemini

### Issues Found
- **Duplicate import**: `from google import genai` appears at line 11 AND line 43
- **Dead code**: `MERGE_WINDOW = 5` defined but never used anywhere
- **`consolidate()` merge logic**: merges `self.episodes[:-10]` — this may lose temporal ordering of older episodes
- **`_save()` IntegrityError**: no handling for unique constraint violation on `(session_id, user_id)`
- **No token count caching**: `_countEpisodeTokens()` recomputes on every call

### Recommendations
1. Remove duplicate import
2. Remove or use `MERGE_WINDOW`
3. Add `try/except IntegrityError` to `_save()`
4. Cache token counts per episode (invalidate on mutation)

---

## 3. Loop Events (A-)

### What's Good
- **Clean separation of concerns**: `events.py` (in-memory buffer) → `agent.py` (persistence calls) → `chat.py` (DB operations)
- **`saveLoopEvent()` with proper error handling**: try/except prevents persistence failures from breaking the chat loop
- **`getHistory()` filters loop events**: LLM never sees `{role: "loop_event"}` messages
- **Frontend integration**: `MessageList.jsx` uses per-message `loopEvents`/`turnMetrics` from persisted data, falls back to live streaming for last message
- **AgentLoop.jsx**: Clean `ToolChip` component with expandable details, status icons (✓/✗/⚡)
- **Observation masking**: `tool_result` NOT persisted — only `tool_call` and `turn_end` events stored
- **`flag_modified`** correctly used for SQLAlchemy JSON column mutation

### Issues Found
- **Duplicated persistence blocks**: `agent.py:305-312` and `:349-362` have identical pattern for `tool_call` and `turn_end` — should be extracted to helper
- **Silent failure**: if session doesn't exist in DB, `saveLoopEvent()` skips silently (no error logged)
- **Frontend fragility**: `loadHistory()` in `App.jsx` has complex nested parsing logic — format changes will break it

### Recommendations
1. Extract the persistence block into a `_persistLoopEvent(eventType, metadata)` helper
2. Add `logger.debug` when session not found in `saveLoopEvent()`
3. Consider a simple schema version field in loop events for forward compatibility

---

## 4. Core Architecture (B+)

### What's Good
- **Clean controller → service → model layering** throughout
- **Dual session pattern**: `Depends(getSession)` for request lifecycle, `SessionLocal()` per streaming request
- **MCP client management** with lazy init (stocks + searxng)
- **Manual function calling loop** — gives full control over tool dispatch (not relying on Gemini SDK's native tool calling)
- **`_safe_filter` monkey-patch** to prevent Gemini from stripping properties from tool schemas
- **System prompt** with ~15 rich UI tag definitions, memory injection, episode context, harness state

### Issues Found
- **`agent.py` too large** (375 lines): does system prompt building, message saving, streaming, tool dispatch, MCP management — should be split
- **`tools.py` opens new `SessionLocal()` per tool call**: no connection pooling benefit, each tool creates a new connection
- **Debug print statement**: `chat.py:117` has `print(f"DEBUG: createSession called for userId={userId}")` — should be removed
- **`dispatchToolCall` missing return type hint**

### Recommendations
1. Split `agent.py` into `prompt.py` (system prompt building) and `agent.py` (orchestration)
2. Consider a tool-level session factory or connection pool
3. Remove debug print statement
4. Add return type hint to `dispatchToolCall`

---

## 5. Security (B+)

### What's Good
- **No hardcoded secrets** — all from `Config` class
- **Parameterized SQL queries** throughout (SQLAlchemy ORM)
- **No XSS innerHTML usage** — React JSX handles escaping
- **Host path validation** in `sandbox.py` (`is_relative_to()`) prevents directory traversal
- **Per-user locks** in `sandbox.py` via `asyncio.Lock`
- **Rate limiting** on controller (5/minute per user)
- **Session ownership verification** before all operations
- **JWT httpOnly cookies** for auth (from auth system)

### Issues Found
- **No CORS validation** for Prometheus endpoints (noted in TODO.md)
- **No resource limits** on sandbox code execution (CPU time, memory) configurable per user
- **`getHistory` returns full history** including loop_events — could leak internal metadata to frontend (frontend handles it, but coupling is fragile)

### Recommendations
1. Add CORS middleware for Prometheus endpoints
2. Add configurable resource limits (timeout, memory) per user tier
3. Consider filtering loop_events at the controller level before sending to frontend

---

## 6. Performance (B)

### What's Good
- **Episode-based summarization** reduces context size (~43% token reduction claimed)
- **Observation masking** saves storage (no tool_result in DB)
- **Vector search with numpy** (fast in-memory computation)
- **FULLTEXT fallback** for search when numpy unavailable
- **Smart truncation** prevents oversized summaries

### Issues Found
- **No embedding cache** — sentence-transformers model loaded on every `embed()` call
- **`tools.py` opens new DB connection per tool call** — no pooling benefit
- **No Redis caching layer** (noted in TODO.md)
- **`memory.py:search()` two separate DB queries** — vector + FULLTEXT could be combined
- **`consolidate()` and `summarize()` both call `self._load()`** — double DB read on every summarization

### Recommendations
1. Add an LRU cache for `embed()` results (or cache the model instance)
2. Consider a shared session factory for tools
3. Cache the loaded episodes in summarizer (invalidate on `_save()`)
4. Evaluate Redis for hot memory/episode lookups

---

## 7. Code Quality (B)

### What's Good
- **Type hints** on most functions
- **Docstrings** on public methods
- **`flag_modified` usage** for SQLAlchemy JSON columns
- **Clean error handling patterns** (try/except with logging)
- **Consistent code style** (ruff-formatted)
- **Test coverage** at 90% (97 tests passing)

### Issues Found
- **`agent.py` too large** (375 lines) — should be split
- **`memory.py` too large** (257 lines) — should be split
- **Duplicate import** in `summarizer.py`
- **Dead code**: `MERGE_WINDOW` in `summarizer.py`
- **Debug print** in `chat.py:117`
- **No `__init__.py` type exports** for prometheus module
- **Some functions missing return type hints** (`dispatchToolCall`)

### Recommendations
1. Split large files into focused modules
2. Clean up dead code and debug statements
3. Add type exports in `__init__.py`
4. Add missing return type hints

---

## Top 5 Priority Fixes

| # | Issue | File | Severity | Effort |
|---|-------|------|----------|--------|
| 1 | `archivedAt` vs `deleted_at` column mismatch | `memory.py:168` | **Critical** (runtime crash) | 5 min |
| 2 | Duplicate import in summarizer | `summarizer.py:11,43` | Low | 2 min |
| 3 | Debug print statement | `chat.py:117` | Low | 2 min |
| 4 | Dead code `MERGE_WINDOW` | `summarizer.py:26` | Low | 2 min |
| 5 | Double embed in `upsertMemory()` | `memory.py` | Medium (perf) | 15 min |

---

## What Changed Since Last Grade

### Before (C+)
- Memory system was partially implemented (no vector embeddings, no FULLTEXT fallback)
- No episode summarization (raw history sent to LLM, token waste)
- No loop event persistence (ephemeral in-memory only)
- No frontend AgentLoop rendering
- No observation masking
- CI pipeline was broken

### After (B+)
- ✅ Full vector embedding memory with cosine similarity
- ✅ MySQL FULLTEXT fallback for Docker environments
- ✅ Jaccard similarity for key dedup
- ✅ Token-based episode summarization with Gemini merge
- ✅ Episode consolidation (cap at 12, merge older)
- ✅ Loop event persistence (tool_call + turn_end in DB)
- ✅ Observation masking (tool_result NOT stored)
- ✅ Frontend AgentLoop with ToolChip rendering
- ✅ Frontend history loading with loop event parsing
- ✅ CI passing (lint, format, mypy, coverage 90%)

### Remaining for A+
- Fix critical bug in `deleteMemory()` (archivedAt column)
- Split `agent.py` into focused modules
- Add embedding cache
- Add Redis caching layer
- Add CORS for Prometheus
- Add resource limits on sandbox execution
