# Orunmila

O Orunmila é um agente chatbot focado no domínio financeiro, com acesso à carteira do usuário (sistema de carteira Iyagba/Thoth, em desenvolvimento), a dados financeiros (Stocks API) e a um sandbox para análises de computação estatística (ForgeVM), com um poderoso sistema de memória. Ele é a proposta de renomeação do Prometheus.

> Nota: os identificadores de código (env `PROMETHEUS_*`, rotas `/prometheus/*`, tabelas `prometheus`) permanecem inalterados até a renomeação posterior do código.

## Usage

1. Environment configuration (`.env`) — `PrometheusSettings` (`config.py:59-71`):

   ```env
   PROMETHEUS_ENABLED=TRUE
   PROMETHEUS_HOST=localhost
   PROMETHEUS_PORT=3200
   GEMINI_API.KEY=your_api_key_here
   SEARXNG_URL=http://searxng:8888
   FORGEVM_URL=http://forgevm:7423
   FORGEVM_API_TOKEN=
   SANDBOX_IMAGE=sandbox-python:latest
   SANDBOX_MEMORY=512
   SANDBOX_CPU=1
   SANDBOX_TTL=5
   WORKSPACE_MAX_UPLOAD_MB=10
   ```

2. Database Schema:

   `prometheus` (`main/models/prometheus.py:7-16`):

   * `sessionId`: String(255) (PK)
   * `userId`: Integer (FK → users.userId, ondelete CASCADE)
   * `title`: String(255)
   * `summary`: Text (nullable, technical memory)
   * `history`: JSON (default `[]`, array of `{role, content, timestamp, metadata}`)
   * `lastActivity`: TIMESTAMP (server_default now, onupdate now)
   * `createdAt`: TIMESTAMP (server_default now)

   `prometheus_memories` (`main/models/memory.py:8-34`):

   * `id`: Integer (PK, autoincrement)
   * `userId`: Integer (indexed)
   * `memoryKey`: String(100)
   * `memoryValue`: Text
   * `memoryType`: String(20), default `"context"`
   * `source`: String(20), default `"inferred"`
   * `score`: Float, default `1.0`
   * `accessCount`: Integer, default `0`
   * `embedding`: Vector(384)
   * `contentHash`: String(32)
   * `createdAt` / `updatedAt`: DateTime (server_default now; `updatedAt` onupdate now)
   * `lastAccessedAt` / `archivedAt`: DateTime (nullable)
   * Constraints: `UniqueConstraint(userId, memoryKey)` (`uk_prometheus_memories`), indexes `idx_relevance(userId, score)` and `idx_type(userId, memoryType)`

3. Run the server:

   ```bash
   python run.py
   ```

## Workflow

30-turn Gemini-native tool-calling loop (`main/app/prometheus/agent.py:52,316,370`):

* `MAX_TURNS = 30` (`agent.py:52`); main loop `while turn < MAX_TURNS` (`agent.py:316`).
* Each turn: stream Gemini chunks → collect `function_calls` → `dispatchToolCall` (MCP sessions + local `TOOL_REGISTRY`) → append tool results → re-send conversation until a text-only turn or `turn_limit`.
* Hitting the cap yields `{"type": "turn_limit", "maxTurns": 30}`.
* Model: `gemini-flash-lite-latest`; chat temperature `0.5` (`agent.py:245,250`), memory extraction temperature `0.2` (`main/app/prometheus/memory.py:493,497`).
* `TOOL_REGISTRY` — 7 tools (`main/app/prometheus/tools.py:179-187`): `search_memory`, `save_memory`, `execute_code`, `read_file`, `write_file`, `list_files`, `serve_file`.
* ForgeVM sandbox per chat turn (`main/app/prometheus/sandbox.py:24-66`): `spawn(image, memory_mb, vcpus, ttl)` from `PROMETHEUS_*` settings; per-user workspace under `/workspace/{userId}` with path-traversal guard (`hostPath`).
* Streaming over SSE via `sse_starlette` (`main/app/prometheus/stream_bus.py:6,109`): `JSONServerSentEvent` generator + `EventSourceResponse(..., ping=15)`.
* Memory (`main/app/prometheus/memory.py`): fused rank `0.6 * vector + 0.25 * fulltext + 0.15 * recency` (`:173`); caps 50 basic / 250 premium (`:72-73`); `rapidfuzz` dedup (`:134`); `cashews` cache matrix (`:30`); deferred BLOB embedding load (`:304`).
* Compaction (`main/app/prometheus/compact.py:20-21`): episode token budget `8000`, episode cap `12`.

## API Endpoints

Router prefix `/prometheus` (`main/controller/prometheus_controller.py`):

* `GET /prometheus/health` — liveness (`:31`).
* `GET /prometheus/sessions` — list user sessions, default `limit=20` (`:36`).
* `PUT /prometheus/sessions/{sessionId}` — rename (`:55`).
* `GET /prometheus/history/{sessionId}` — ownership-protected history (`:70`).
* `DELETE /prometheus/sessions/{sessionId}` — delete (`:89`).
* `POST /prometheus/chat/stream` — start SSE run, 5/min (`:101`).
* `GET /prometheus/chat/stream/{sessionId}` — resume SSE run (`:153`).
* `DELETE /prometheus/workspace/delete` — delete file, 30/min (`:164`).
* `GET /prometheus/workspace/download?path=` — download file (`:178`).
* `GET /prometheus/workspace/list?path=/workspace` — list files (`:194`).

## License

Mansa Team's MODIFIED GPL 3.0 License. See LICENSE for details.
