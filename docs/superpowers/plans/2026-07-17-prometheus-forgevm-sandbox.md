# Prometheus ForgeVM Sandbox — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Claude/Kimi-style persistent sandbox to Prometheus using ForgeVM — per-user isolated containers with full filesystem access, code execution, and resource limits. Docker provider on Windows (runc), Firecracker provider on Linux (KVM).

**Architecture:** Ephemeral containers + persistent volumes. Each user gets a persistent volume (`/data/workspaces/{userId}/`). Containers are spawned on-demand, mounted to the user's volume, destroyed when done. The volume survives, the container doesn't.

```
User 123: "Analyze PETR4 vs VALE3 correlation"
    ↓
streamMessage() creates:
    state = HarnessState()
    sandbox_id = None  # on-demand only
    ↓
┌──────────────────────────────────────────────────────────────┐
│  LLM: "I'll analyze both stocks"                            │
│  + function_call: get_fundamental(search="PETR4,VALE3")      │
│    ↓                                                          │
│  dispatchToolCall → MCP routes to stocks client              │
│    ↓                                                          │
│  LLM: execute_code(code="import pandas as pd; ...")          │
│    ↓                                                          │
│  CHECK: is_premium(user) → YES                               │
│  CHECK: sandbox_id exists? → NO                              │
│  CREATE: SandboxManager.create(userId=123)                   │
│    → ForgeVM spawns container                                │
│    → mounts /data/workspaces/123/ → /workspace               │
│    → returns sandbox_id                                      │
│  EXECUTE: SandboxManager.execute(sandbox_id, code)           │
│    → ForgeVM exec in container                               │
│    → stdout/stderr returned                                  │
│    ↓                                                          │
│  LLM: read_file(path="/workspace/results.json")              │
│    → ForgeVM reads from /workspace (which is user's volume)  │
│    ↓                                                          │
│  LLM formats response with {% table %} + {% chart %}         │
│    ↓                                                          │
│  Container destroyed (volume persists for next session)      │
└──────────────────────────────────────────────────────────────┘
```

## Global Constraints

- Python 3.11, FastAPI, SQLAlchemy, Pydantic BaseSettings
- Env vars use dotted names via `AliasChoices` pattern
- `ruff check . && ruff format .` before commit
- `.\ci.ps1` must pass (lint, format, mypy, pytest+coverage ≥80%, bandit)
- Ponytail mode: shortest working diff, no unrequested abstractions
- ForgeVM: `pip install forgevm` (v0.1.2, MIT)
- Sandbox is on-demand: created only when LLM calls execute_code
- Sandbox is premium-only: free users get chat-only mode
- Per-user volumes persist across sessions
- Containers are ephemeral: destroyed at session end
- Provider swap is config-only: Docker (Windows) → Firecracker (Linux)

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `config.py` | Modify | Add `FORGEVM_URL`, `WORKSPACE_ROOT`, `SANDBOX_IMAGE` to PrometheusSettings |
| `main/app/prometheus/sandbox.py` | Create | `SandboxManager` — ForgeVM REST API client (create, execute, read_file, write_file, list_files, destroy) |
| `main/app/prometheus/tools.py` | Modify | Add sandbox tool functions (execute_code, read_file, write_file, list_files) to TOOL_REGISTRY |
| `main/app/prometheus/agent.py` | Modify | Integrate on-demand sandbox lifecycle into streamMessage |
| `docker-compose.yml` | Modify | Add ForgeVM service, workspace volume |
| `Dockerfile.sandbox` | Create | Python data science image (pandas, numpy, scipy, plotly) |
| `tests/test_sandbox.py` | Create | Tests for SandboxManager |
| `tests/test_sandbox_tools.py` | Create | Tests for sandbox tools + dispatch routing |
| `tests/test_agent_sandbox_integration.py` | Create | Tests for agent sandbox integration |

---

## Phase 1: Config + ForgeVM Setup

### Task 1: Config — Add ForgeVM Settings

**Files:**
- Modify: `config.py` (PrometheusSettings class)

- [ ] **Step 1: Add fields to PrometheusSettings**

```python
class PrometheusSettings(BaseMansaSettings):
    # ... existing fields ...
    FORGEVM_URL: str = Field(default="http://localhost:7423", validation_alias=AliasChoices("FORGEVM_URL"))
    WORKSPACE_ROOT: str = Field(default="/data/workspaces", validation_alias=AliasChoices("WORKSPACE_ROOT"))
    SANDBOX_IMAGE: str = Field(default="python-data-science", validation_alias=AliasChoices("SANDBOX_IMAGE"))
    SANDBOX_MEMORY_MB: int = Field(default=2048, validation_alias=AliasChoices("SANDBOX_MEMORY_MB"))
    SANDBOX_CPUS: int = Field(default=2, validation_alias=AliasChoices("SANDBOX_CPUS"))
    SANDBOX_TTL_MINUTES: int = Field(default=30, validation_alias=AliasChoices("SANDBOX_TTL_MINUTES"))
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "add ForgeVM sandbox config fields"
```

---

### Task 2: Docker Compose — Add ForgeVM Service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add ForgeVM service + workspace volume**

```yaml
services:
  # ... existing services ...

  forgevm:
    build:
      context: .
      dockerfile: Dockerfile.forgevm
    restart: always
    ports:
      - "7423:7423"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - forgevm-data:/data
      - workspaces:/data/workspaces
    environment:
      - FORGEVM_DATABASE_PATH=/data/forgevm.db
      - FORGEVM_PROVIDER=docker
      - FORGEVM_LOGGING_LEVEL=info

volumes:
  db_data:
  forgevm-data:
  workspaces:
```

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "add ForgeVM service and workspace volume to docker-compose"
```

---

## Phase 2: SandboxManager

### Task 3: ForgeVM REST API Client

**Files:**
- Create: `main/app/prometheus/sandbox.py`
- Create: `tests/test_sandbox.py`

**Design:** Stateless class with `@staticmethod` methods. Each method creates its own `httpx.AsyncClient`. Follows the same pattern as the original SandboxManager but targets ForgeVM's API.

- [ ] **Step 1: Write tests**

Create `tests/test_sandbox.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from main.app.prometheus.sandbox import SandboxManager


class TestSandboxManager:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_create_sandbox(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"id": "sb-123", "status": "running"}
        mock_resp.raise_for_status = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await SandboxManager.create(userId=1)
        assert result["id"] == "sb-123"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_execute_code(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"stdout": "Hello\n", "stderr": ""}
        mock_resp.raise_for_status = AsyncMock()
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await SandboxManager.execute("sb-123", "print('Hello')")
        assert result["stdout"] == "Hello\n"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_read_file(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"content": "file contents"}
        mock_resp.raise_for_status = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await SandboxManager.read_file("sb-123", "/workspace/data.csv")
        assert result["content"] == "file contents"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_write_file(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.status_code = 200
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await SandboxManager.write_file("sb-123", "/workspace/test.py", "print(42)")
        assert result is True

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_list_files(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.json.return_value = {"entries": [{"name": "data.csv", "type": "file"}]}
        mock_resp.raise_for_status = AsyncMock()
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        result = await SandboxManager.list_files("sb-123", "/workspace")
        assert len(result["entries"]) == 1

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_destroy_sandbox(self, mock_cls):
        mock_resp = AsyncMock()
        mock_resp.raise_for_status = AsyncMock()
        mock_client = AsyncMock()
        mock_client.delete.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        await SandboxManager.destroy("sb-123")
        mock_client.delete.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.httpx.AsyncClient")
    async def test_destroy_handles_failure(self, mock_cls):
        mock_client = AsyncMock()
        mock_client.delete.side_effect = Exception("connection refused")
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_cls.return_value = mock_client
        # Should not raise
        await SandboxManager.destroy("sb-123")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sandbox.py -v`
Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

Create `main/app/prometheus/sandbox.py`:

```python
import logging
import os

import httpx

from config import Config

logger = logging.getLogger(__name__)

FORGEVM_URL = Config.PROMETHEUS.get("FORGEVM_URL", "http://localhost:7423")
WORKSPACE_ROOT = Config.PROMETHEUS.get("WORKSPACE_ROOT", "/data/workspaces")
SANDBOX_IMAGE = Config.PROMETHEUS.get("SANDBOX_IMAGE", "python-data-science")
SANDBOX_MEMORY_MB = Config.PROMETHEUS.get("SANDBOX_MEMORY_MB", 2048)
SANDBOX_CPUS = Config.PROMETHEUS.get("SANDBOX_CPUS", 2)
SANDBOX_TTL_MINUTES = Config.PROMETHEUS.get("SANDBOX_TTL_MINUTES", 30)


class SandboxManager:
    """ForgeVM sandbox manager — ephemeral containers with persistent per-user volumes."""

    @staticmethod
    async def create(userId: int) -> str:
        """Create a sandbox for a user. Mounts their persistent volume at /workspace."""
        user_volume = os.path.join(WORKSPACE_ROOT, str(userId))
        os.makedirs(user_volume, exist_ok=True)

        async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=30) as client:
            resp = await client.post(
                "/api/v1/sandboxes",
                json={
                    "image": SANDBOX_IMAGE,
                    "memory_mb": SANDBOX_MEMORY_MB,
                    "vcpus": SANDBOX_CPUS,
                    "ttl_minutes": SANDBOX_TTL_MINUTES,
                    "network": "none",
                    "volumes": {"/workspace": user_volume},
                    "metadata": {"userId": str(userId)},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            sandbox_id = data["id"]
            logger.info("Sandbox created: %s for user %d", sandbox_id, userId)
            return sandbox_id

    @staticmethod
    async def execute(sandboxId: str, code: str, timeout: int = 30) -> dict:
        """Execute Python code in the sandbox."""
        async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=timeout + 5) as client:
            resp = await client.post(
                f"/api/v1/sandboxes/{sandboxId}/exec",
                json={"command": f"python3 -c '{code}'", "timeout": timeout},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def read_file(sandboxId: str, path: str) -> str:
        """Read a file from the sandbox filesystem."""
        async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=30) as client:
            resp = await client.get(
                f"/api/v1/sandboxes/{sandboxId}/files",
                params={"path": path},
            )
            resp.raise_for_status()
            return resp.json().get("content", "")

    @staticmethod
    async def write_file(sandboxId: str, path: str, content: str) -> bool:
        """Write a file to the sandbox filesystem."""
        async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=30) as client:
            resp = await client.post(
                f"/api/v1/sandboxes/{sandboxId}/files",
                json={"path": path, "content": content},
            )
            return resp.status_code < 400

    @staticmethod
    async def list_files(sandboxId: str, path: str = "/workspace") -> dict:
        """List files in a sandbox directory."""
        async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=30) as client:
            resp = await client.get(
                f"/api/v1/sandboxes/{sandboxId}/files/list",
                params={"path": path},
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def destroy(sandboxId: str) -> None:
        """Destroy sandbox. Volume persists on host."""
        try:
            async with httpx.AsyncClient(base_url=FORGEVM_URL, timeout=15) as client:
                await client.delete(f"/api/v1/sandboxes/{sandboxId}")
                logger.info("Sandbox destroyed: %s", sandboxId)
        except Exception as e:
            logger.warning("Failed to destroy sandbox %s: %s", sandboxId, e)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sandbox.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/sandbox.py tests/test_sandbox.py
git commit -m "add SandboxManager with ForgeVM REST API client"
```

---

## Phase 3: Sandbox Tools

### Task 4: Tool Definitions — Sandbox Tools in TOOL_REGISTRY

**Files:**
- Modify: `main/app/prometheus/tools.py`
- Create: `tests/test_sandbox_tools.py`

- [ ] **Step 1: Write tests**

Create `tests/test_sandbox_tools.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main.app.prometheus.tools import TOOL_REGISTRY, dispatchToolCall


class TestSandboxToolDefinitions:
    def test_execute_code_in_registry(self):
        assert "execute_code" in TOOL_REGISTRY

    def test_read_file_in_registry(self):
        assert "read_file" in TOOL_REGISTRY

    def test_write_file_in_registry(self):
        assert "write_file" in TOOL_REGISTRY

    def test_list_files_in_registry(self):
        assert "list_files" in TOOL_REGISTRY

    def test_execute_code_has_docstring(self):
        fn = TOOL_REGISTRY["execute_code"]
        assert fn.__doc__ is not None
        assert len(fn.__doc__) > 20


class TestDispatchToolCallSandbox:
    @pytest.mark.anyio
    @patch("main.app.prometheus.tools.SandboxManager")
    async def test_dispatch_execute_code(self, mock_sandbox):
        mock_fc = MagicMock()
        mock_fc.name = "execute_code"
        mock_fc.args = {"code": "print(42)", "timeout": 10}
        mock_sandbox.execute = AsyncMock(return_value={"stdout": "42\n", "stderr": ""})
        result = await dispatchToolCall(
            mock_fc, {}, user={"userId": 1}, sandbox_id="sb-123"
        )
        assert result["stdout"] == "42\n"
        mock_sandbox.execute.assert_called_once_with("sb-123", "print(42)", 10)

    @pytest.mark.anyio
    async def test_dispatch_execute_code_no_sandbox(self):
        mock_fc = MagicMock()
        mock_fc.name = "execute_code"
        mock_fc.args = {"code": "print(42)"}
        result = await dispatchToolCall(
            mock_fc, {}, user={"userId": 1}, sandbox_id=None
        )
        assert "error" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sandbox_tools.py -v`
Expected: FAIL — `execute_code` not in TOOL_REGISTRY

- [ ] **Step 3: Write the implementation**

Add to `main/app/prometheus/tools.py`:

```python
from main.app.prometheus.sandbox import SandboxManager


# --- sandbox tools ---


async def execute_code(code: str, timeout: int = 30, **_) -> dict:
    """Execute Python code in an isolated sandbox. Use for quantitative analysis,
    statistical models, custom charts, and data transformations.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 30)
    """
    sandbox_id = _.get("sandbox_id")
    if not sandbox_id:
        return {"error": "Sandbox not available. This feature requires a premium subscription."}

    result = await SandboxManager.execute(sandbox_id, code, timeout=timeout)
    return {
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }


async def read_file(path: str, **_) -> dict:
    """Read a file from the sandbox filesystem.

    Args:
        path: Absolute path to the file in the sandbox (e.g., /workspace/results.json)
    """
    sandbox_id = _.get("sandbox_id")
    if not sandbox_id:
        return {"error": "Sandbox not available"}
    content = await SandboxManager.read_file(sandbox_id, path)
    return {"content": content}


async def write_file(path: str, content: str, **_) -> dict:
    """Write a file to the sandbox filesystem. Use this to push data files
    (CSV, JSON, scripts) into the sandbox before running analysis code.

    Args:
        path: Absolute path where the file will be written (e.g., /workspace/analyze.py)
        content: File content as a string
    """
    sandbox_id = _.get("sandbox_id")
    if not sandbox_id:
        return {"error": "Sandbox not available"}
    ok = await SandboxManager.write_file(sandbox_id, path, content)
    return {"success": ok}


async def list_files(path: str = "/workspace", **_) -> dict:
    """List files in a sandbox directory. Use to explore the workspace
    and find previously created files.

    Args:
        path: Directory path to list (default: /workspace)
    """
    sandbox_id = _.get("sandbox_id")
    if not sandbox_id:
        return {"error": "Sandbox not available"}
    return await SandboxManager.list_files(sandbox_id, path)
```

Update `TOOL_REGISTRY`:

```python
TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "get_state": get_state,
    "set_state": set_state,
    "execute_code": execute_code,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
}
```

Update `dispatchToolCall` signature to accept `sandbox_id`:

```python
async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    state=None,
    sandbox_id: str | None = None,
) -> dict:
    name = functionCall.name
    args = dict(functionCall.args or {})
    logger.info(f"Executing tool call: {name}({args})")

    if name in TOOL_REGISTRY:
        fn = TOOL_REGISTRY[name]
        args["user"] = user
        args["state"] = state
        args["sandbox_id"] = sandbox_id
        return await fn(**args)
    # ... rest unchanged
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sandbox_tools.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/tools.py tests/test_sandbox_tools.py
git commit -m "add sandbox tools (execute_code, read_file, write_file, list_files) to TOOL_REGISTRY"
```

---

## Phase 4: Agent Integration

### Task 5: Agent — On-Demand Sandbox + Premium Gating

**Files:**
- Modify: `main/app/prometheus/agent.py`
- Create: `tests/test_agent_sandbox_integration.py`

- [ ] **Step 1: Write tests**

Create `tests/test_agent_sandbox_integration.py`:

```python
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from main.app.prometheus.agent import Prometheus
from main.app.prometheus.state import HarnessState


class TestAgentSandboxIntegration:
    def test_build_system_prompt_includes_sandbox_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "execute_code" in prompt
        assert "read_file" in prompt
        assert "write_file" in prompt

    def test_build_system_prompt_includes_state_instructions(self):
        prompt = Prometheus.buildSystemPrompt()
        assert "set_state" in prompt
        assert "get_state" in prompt

    def test_build_system_prompt_with_state(self):
        state = HarnessState()
        state.set("current_step", "3/5")
        prompt = Prometheus.buildSystemPrompt(state=state)
        assert "[HARNESS STATE]" in prompt
        assert "- current_step: 3/5" in prompt
```

- [ ] **Step 2: Update agent.py**

Update imports:

```python
from main.app.prometheus.sandbox import SandboxManager
```

Update `streamMessage` — add on-demand sandbox creation:

```python
async def streamMessage(self, query=None, sessionId=None, db=None, user=None) -> AsyncIterator[dict]:
    history = PrometheusChatManager.getHistory(db, str(sessionId), limit=50)
    state = HarnessState()
    loop = LoopLogger(history)
    sandbox_id = None  # on-demand only

    system_prompt = Prometheus.buildSystemPrompt(user.get("userId") if user else None, db, state=state)

    try:
        async with self.openMCPClients() as (mcpClients, sessions):
            chat = self.makeChat(
                sessions, history, system_prompt=system_prompt, disable_automatic_function_calling=True
            )
            stream = await chat.send_message_stream(query)
            fullText = ""
            turn = 0

            while True:
                chunks_text = ""
                function_calls: list = []
                async for chunk in stream:
                    if hasattr(chunk, "text") and chunk.text:
                        chunks_text += chunk.text
                        yield {"type": "text", "text": chunk.text}
                    if hasattr(chunk, "function_calls") and chunk.function_calls:
                        fcs = chunk.function_calls
                        function_calls.extend(fcs.values() if isinstance(fcs, dict) else fcs)
                fullText += chunks_text

                if not function_calls:
                    break

                turn_start = int(__import__("time").time() * 1000)
                tools_used = []
                responses = []

                for fc in function_calls:
                    tools_used.append(fc.name)
                    loop.emit_tool_call(fc.name, fc.args or {}, turnNumber=turn)

                    # On-demand sandbox creation
                    if fc.name == "execute_code" and sandbox_id is None:
                        is_premium = user and user.get("isPremium", False)
                        if is_premium:
                            try:
                                sandbox_id = await SandboxManager.create(user.get("userId", 0))
                                logger.info("On-demand sandbox created: %s", sandbox_id)
                            except Exception as e:
                                logger.warning("Sandbox creation failed: %s", e)
                                responses.append(
                                    types.Part.from_function_response(
                                        name=fc.name, response={"error": "Sandbox unavailable."}
                                    )
                                )
                                continue
                        else:
                            responses.append(
                                types.Part.from_function_response(
                                    name=fc.name, response={"error": "Sandbox requires premium subscription."}
                                )
                            )
                            continue

                    result = await dispatchToolCall(
                        fc, mcpClients, user=user, state=state, sandbox_id=sandbox_id
                    )
                    loop.emit_tool_result(fc.name, result, turnNumber=turn)
                    responses.append(types.Part.from_function_response(name=fc.name, response=result))

                if state.has_changed():
                    responses.append(
                        types.Part.from_text(text=f"\n[HARNESS STATE]\n{state.to_context()}\n[/HARNESS STATE]")
                    )
                    state.reset_changed()

                loop.emit_turn_end(
                    turnNumber=turn,
                    durationMs=int(__import__("time").time() * 1000) - turn_start,
                    toolsUsed=tools_used,
                )
                turn += 1
                stream = await chat.send_message_stream(responses)

        PrometheusChatManager.saveMessage(db, str(sessionId), "user", str(query))
        if fullText:
            PrometheusChatManager.saveMessage(db, str(sessionId), "assistant", fullText)
    finally:
        if sandbox_id:
            try:
                await SandboxManager.destroy(sandbox_id)
            except Exception as e:
                logger.warning("Sandbox cleanup failed: %s", e)
        loop.flush()
```

- [ ] **Step 3: Update system prompt**

Add to `SYSTEM_PROMPT` (after "Harness State" section):

```python
        ## Code Sandbox (On-Demand)
        You have access to an isolated Python sandbox for quantitative analysis.
        The sandbox is created automatically when you first call execute_code.
        Only available for premium users.

        Use execute_code for: statistical analysis, DCF models, correlation matrices,
        Monte Carlo simulations, custom charts, data transformations.

        Use write_file to push data files (CSV, JSON) into the sandbox before running code.
        Use read_file to read results from the sandbox.
        Use list_files to explore the workspace.

        Access stock data via MCP tools (get_fundamental, get_historical, get_cotations)
        before running sandbox code — pass the data as variables in your code.

        Libraries available: pandas, numpy, scipy, plotly, matplotlib, requests.
        Save charts to /workspace/ as .html (plotly) or .png (matplotlib).
        Always print() key findings so they appear in stdout.
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent_sandbox_integration.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/agent.py tests/test_agent_sandbox_integration.py
git commit -m "integrate on-demand ForgeVM sandbox with premium gating into agent"
```

---

## Phase 5: Docker Image + Final Verification

### Task 6: Dockerfile.sandbox — Python Data Science Image

**Files:**
- Create: `Dockerfile.sandbox`

- [ ] **Step 1: Create the Dockerfile**

```dockerfile
FROM python:3.11-slim

RUN pip install --no-cache-dir \
    pandas numpy scipy scikit-learn \
    plotly matplotlib seaborn \
    statsmodels \
    requests httpx \
    openpyxl xlrd \
    beautifulsoup4 \
    sympy

RUN mkdir -p /workspace /tmp
WORKDIR /workspace
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile.sandbox
git commit -m "add Python data science sandbox image"
```

---

### Task 7: Full CI Verification

- [ ] **Step 1: Run full CI**

Run: `.\ci.ps1`
Expected: All checks pass (lint, format, mypy, pytest+coverage ≥80%, bandit non-blocking)

- [ ] **Step 2: Manual smoke test (optional, requires Docker)**

```bash
docker-compose up -d --build
# Test ForgeVM is running
curl http://localhost:7423/health
# Test sandbox creation via API
curl -X POST http://localhost:7423/api/v1/sandboxes -d '{"image":"python-data-science"}'
```

---

## Summary

| Phase | Task | Deliverable | Lines |
|---|---|---|---|
| **1. Config** | Task 1 | Config fields (FORGEVM_URL, WORKSPACE_ROOT, etc.) | ~10 |
| | Task 2 | docker-compose ForgeVM service + volumes | ~15 |
| **2. SandboxManager** | Task 3 | `sandbox.py` — ForgeVM REST client (6 methods) | ~80 |
| **3. Tools** | Task 4 | sandbox tools in TOOL_REGISTRY + dispatch wiring | ~60 |
| **4. Agent** | Task 5 | Agent integration (on-demand + premium gating) | ~50 |
| **5. Docker** | Task 6 | Dockerfile.sandbox | ~10 |
| | Task 7 | CI verification | — |

**Total: ~225 lines across 7 files (4 new, 3 modified).**

---

## What This Enables

1. **On-demand sandbox** — created ONLY when LLM calls execute_code
2. **Premium gating** — free users get chat-only, premium users get sandbox
3. **Per-user isolation** — each user's volume is exclusive
4. **Full filesystem access** — agent can read/write files in /workspace
5. **Code execution** — Python with pandas/numpy/scipy in isolated container
6. **Resource limits** — CPU/memory/disk/TTL per container
7. **Persistent workspace** — volume survives container destroy/recreate
8. **Provider swap** — Docker (Windows) → Firecracker (Linux) via config change

## What This Does NOT Do (By Design)

- Does NOT create sandbox at session start — on-demand only
- Does NOT persist state across requests (except via persistent volumes)
- Does NOT add browser automation (future: Playwright in container)
- Does NOT add cross-session state persistence (volume files persist, but app-level sync needed)
- Does NOT touch MySQL for state — pure in-memory + filesystem
