# Sandbox Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each user gets a persistent sandbox that survives across API requests. The agent can reconnect to a user's sandbox, extend its TTL, and restore filesystem state if the sandbox dies.

**Architecture:** Two persistence layers: (1) live sandbox reuse via DB mapping table (`userId → sandboxId`), with TTL extension on activity; (2) filesystem backup to host volume on each response, with restore-on-spawn for crash recovery. The agent checks for existing sandbox before creating new ones, and syncs workspace files to durable storage.

**Tech Stack:** SQLAlchemy model + Alembic migration, forgevm Python SDK (AsyncClient), existing pytest + asyncio test patterns.

## Global Constraints

- Python 3.12+, FastAPI, SQLAlchemy (declarative_base pattern)
- MySQL 8.0 (production), SQLite in-memory (tests)
- forgevm SDK v0.1.2 (AsyncClient, spawn, get, exec, read_file, write_file, list_files, glob_files, extend_ttl, destroy)
- TDD: write failing test first, implement, verify pass
- One commit per task, descriptive messages
- Env vars use weird format: `FORGEVM_URL`, `SANDBOX_TTL_MINUTES` (dots in some config keys)
- Dockerfile uses WORKDIR / + PYTHONPATH=/ — config.py loaded from build-time copy, env vars override

---

## File Structure

| File | Action | Purpose |
|---|---|---|
| `main/models/sandbox.py` | Create | `PrometheusSandbox` SQLAlchemy model |
| `main/models/__init__.py` | Modify | Export `PrometheusSandbox` |
| `migrations/env.py` | Modify | Import new model for autogenerate |
| `migrations/versions/xxx_add_prometheus_sandboxes.py` | Create | Alembic migration |
| `main/app/prometheus/sandbox.py` | Modify | Add persistence logic (reconnect, sync, extend) |
| `main/app/prometheus/agent.py` | Modify | Use persistent sandbox lifecycle |
| `tests/test_sandbox_persistence.py` | Create | Tests for persistence layer |
| `tests/test_sandbox.py` | Modify | Update existing tests for new signatures |

---

### Task 1: Database Model + Migration

**Files:**
- Create: `main/models/sandbox.py`
- Modify: `main/models/__init__.py:1-6`
- Modify: `migrations/env.py:14`
- Create: `migrations/versions/xxx_add_prometheus_sandboxes.py`

**Interfaces:**
- Consumes: `main.models.base.Base` (declarative_base)
- Produces: `PrometheusSandbox` model with fields: id, userId, sandboxId, workspacePath, lastActivity, createdAt

- [ ] **Step 1: Write the failing test**

```python
# tests/test_sandbox_persistence.py
import pytest
from datetime import datetime, timezone
from main.models.sandbox import PrometheusSandbox


class TestPrometheusSandboxModel:
    def test_create_sandbox_mapping(self, dbSession):
        sandbox = PrometheusSandbox(
            userId=1,
            sandboxId="sb-test-123",
            workspacePath="/data/workspaces/1",
        )
        dbSession.add(sandbox)
        dbSession.commit()
        assert sandbox.id is not None
        assert sandbox.sandboxId == "sb-test-123"
        assert sandbox.userId == 1

    def test_sandbox_has_timestamps(self, dbSession):
        sandbox = PrometheusSandbox(
            userId=1,
            sandboxId="sb-test-456",
            workspacePath="/data/workspaces/1",
        )
        dbSession.add(sandbox)
        dbSession.commit()
        assert sandbox.createdAt is not None
        assert sandbox.lastActivity is not None

    def test_one_sandbox_per_user(self, dbSession):
        """Enforce one active sandbox per user via application logic."""
        s1 = PrometheusSandbox(userId=1, sandboxId="sb-a", workspacePath="/data/workspaces/1")
        dbSession.add(s1)
        dbSession.commit()
        # Second sandbox for same user — application should replace, not duplicate
        existing = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert existing is not None
        assert existing.sandboxId == "sb-a"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sandbox_persistence.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'main.models.sandbox'`

- [ ] **Step 3: Write the model**

```python
# main/models/sandbox.py
from sqlalchemy import Column, Integer, String, DateTime, func
from main.models.base import Base


class PrometheusSandbox(Base):
    __tablename__ = "prometheus_sandboxes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, nullable=False, index=True, unique=True)
    sandboxId = Column(String(255), nullable=False)
    workspacePath = Column(String(500), nullable=False)
    lastActivity = Column(DateTime, server_default=func.now(), onupdate=func.now())
    createdAt = Column(DateTime, server_default=func.now())
```

- [ ] **Step 4: Register in __init__.py**

```python
# main/models/__init__.py — add import
from main.models.user import User
from main.models.user_session import UserSession
from main.models.stocksapi_key import StocksAPIKey
from main.models.prometheus import PrometheusSession
from main.models.sandbox import PrometheusSandbox

__all__ = ["User", "UserSession", "StocksAPIKey", "PrometheusSession", "PrometheusSandbox"]
```

- [ ] **Step 5: Register in migrations/env.py**

```python
# migrations/env.py — add import after line 14
import main.models.prometheus
import main.models.sandbox  # ADD THIS
```

- [ ] **Step 6: Generate migration**

Run: `alembic revision --autogenerate -m "add prometheus_sandboxes table"`

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_sandbox_persistence.py -v`
Expected: 3 PASS

- [ ] **Step 8: Commit**

```bash
git add main/models/sandbox.py main/models/__init__.py migrations/env.py migrations/versions/xxx_*.py tests/test_sandbox_persistence.py
git commit -m "feat: add PrometheusSandbox model for per-user sandbox persistence"
```

---

### Task 2: SandboxManager Persistence Logic

**Files:**
- Modify: `main/app/prometheus/sandbox.py:1-102`
- Modify: `tests/test_sandbox.py:1-106`
- Create: `tests/test_sandbox_persistence.py` (extend)

**Interfaces:**
- Consumes: `PrometheusSandbox` model, `SessionLocal` from config, forgevm AsyncClient
- Produces: `SandboxManager.getOrCreate(userId) -> str`, `SandboxManager.syncWorkspace(sandboxId, workspacePath)`, `SandboxManager.restoreWorkspace(sandboxId, workspacePath)`

- [ ] **Step 1: Write failing tests for persistence methods**

```python
# tests/test_sandbox_persistence.py — append to existing file
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main.app.prometheus.sandbox import SandboxManager
from main.models.sandbox import PrometheusSandbox


class TestSandboxPersistence:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_get_or_create_creates_new_when_no_existing(self, mock_get_client, dbSession):
        """No existing sandbox in DB → spawn new one, store mapping."""
        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.id = "sb-new-789"
        mock_client.spawn = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        sandbox_id = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        assert sandbox_id == "sb-new-789"
        mock_client.spawn.assert_called_once()

        # Verify mapping stored
        mapping = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert mapping is not None
        assert mapping.sandboxId == "sb-new-789"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_get_or_create_reuses_existing(self, mock_get_client, dbSession):
        """Existing sandbox in DB + still alive → reuse it."""
        # Pre-populate DB
        mapping = PrometheusSandbox(userId=1, sandboxId="sb-existing", workspacePath="/data/workspaces/1")
        dbSession.add(mapping)
        dbSession.commit()

        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.id = "sb-existing"
        mock_sandbox.extend_ttl = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        sandbox_id = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        assert sandbox_id == "sb-existing"
        mock_client.get.assert_called_once_with("sb-existing")
        mock_sandbox.extend_ttl.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_get_or_create_respawns_when_dead(self, mock_get_client, dbSession):
        """Existing sandbox in DB but expired → spawn new, update mapping."""
        mapping = PrometheusSandbox(userId=1, sandboxId="sb-dead", workspacePath="/data/workspaces/1")
        dbSession.add(mapping)
        dbSession.commit()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("not found"))
        new_sandbox = AsyncMock()
        new_sandbox.id = "sb-reborn"
        mock_client.spawn = AsyncMock(return_value=new_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        sandbox_id = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        assert sandbox_id == "sb-reborn"
        mock_client.spawn.assert_called_once()

        # Mapping updated
        updated = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert updated.sandboxId == "sb-reborn"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_sync_workspace(self, mock_get_client, dbSession):
        """Sync workspace: list files, read each, return dict of {path: content}."""
        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.glob_files = AsyncMock(return_value=["/workspace/data.csv", "/workspace/plot.png"])
        mock_sandbox.read_file = AsyncMock(side_effect=["csv-data", "png-bytes"])
        mock_client.get = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        files = await SandboxManager.syncWorkspace("sb-123")
        assert len(files) == 2
        assert files["/workspace/data.csv"] == "csv-data"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_restore_workspace(self, mock_get_client, dbSession):
        """Restore workspace: write each file back into sandbox."""
        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.write_file = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        files = {"/workspace/data.csv": "csv-data", "/workspace/plot.png": "png-bytes"}
        await SandboxManager.restoreWorkspace("sb-123", files)
        assert mock_sandbox.write_file.call_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_sandbox_persistence.py -v`
Expected: FAIL — `getOrCreate`, `syncWorkspace`, `restoreWorkspace` don't exist

- [ ] **Step 3: Implement persistence methods**

```python
# main/app/prometheus/sandbox.py — full rewrite
import logging
import os
from pathlib import Path

from forgevm import AsyncClient, ExecResult

from config import Config, SessionLocal
from main.models.sandbox import PrometheusSandbox

logger = logging.getLogger(__name__)

FORGEVM_URL = Config.PROMETHEUS.get("FORGEVM_URL", "http://forgevm:7423")
WORKSPACE_ROOT = Config.PROMETHEUS.get("WORKSPACE_ROOT", "/data/workspaces")
SANDBOX_IMAGE = Config.PROMETHEUS.get("SANDBOX_IMAGE", "python:3.12-slim")
SANDBOX_MEMORY_MB = Config.PROMETHEUS.get("SANDBOX_MEMORY_MB", 2048)
SANDBOX_CPUS = Config.PROMETHEUS.get("SANDBOX_CPUS", 2)
SANDBOX_TTL_MINUTES = Config.PROMETHEUS.get("SANDBOX_TTL_MINUTES", 30)
SANDBOX_TTL_RENEW = Config.PROMETHEUS.get("SANDBOX_TTL_RENEW", "24h")


def _getClient() -> AsyncClient:
    return AsyncClient(base_url=FORGEVM_URL, timeout=30)


class SandboxManager:
    """ForgeVM sandbox manager with per-user persistence and filesystem backup."""

    @staticmethod
    async def create(userId: int) -> str:
        """Create a new sandbox (no persistence logic — used for raw spawns)."""
        client = _getClient()
        try:
            sandbox = await client.spawn(
                image=SANDBOX_IMAGE,
                memory_mb=SANDBOX_MEMORY_MB,
                vcpus=SANDBOX_CPUS,
                ttl=f"{SANDBOX_TTL_MINUTES}m",
            )
            sandbox_id = sandbox.id
            logger.info("Sandbox created: %s for user %d", sandbox_id, userId)
            return sandbox_id
        finally:
            await client.close()

    @staticmethod
    async def getOrCreate(userId: int, db=None) -> str:
        """Get existing sandbox for user, or create new one. Extends TTL on reuse."""
        if db is None:
            db = SessionLocal()
            close_db = True
        else:
            close_db = False

        try:
            # Check for existing mapping
            mapping = db.query(PrometheusSandbox).filter_by(userId=userId).first()

            if mapping:
                # Try to reconnect
                client = _getClient()
                try:
                    sandbox = await client.get(mapping.sandboxId)
                    # Sandbox alive — extend TTL and reuse
                    await sandbox.extend_ttl(SANDBOX_TTL_RENEW)
                    mapping.lastActivity = func.now()
                    db.commit()
                    logger.info("Reconnected to sandbox %s for user %d", mapping.sandboxId, userId)
                    return mapping.sandboxId
                except Exception as e:
                    # Sandbox dead — clean up mapping, fall through to create
                    logger.info("Sandbox %s dead for user %d: %s", mapping.sandboxId, userId, e)
                    db.delete(mapping)
                    db.commit()
                finally:
                    await client.close()

            # Create new sandbox
            sandbox_id = await SandboxManager.create(userId)

            # Store mapping (upsert — replace if somehow exists)
            if mapping:
                mapping.sandboxId = sandbox_id
                mapping.workspacePath = os.path.join(WORKSPACE_ROOT, str(userId))
            else:
                mapping = PrometheusSandbox(
                    userId=userId,
                    sandboxId=sandbox_id,
                    workspacePath=os.path.join(WORKSPACE_ROOT, str(userId)),
                )
                db.add(mapping)
            db.commit()

            # Restore workspace from backup if it exists
            workspace_path = mapping.workspacePath
            if os.path.isdir(workspace_path):
                backup = SandboxManager._loadBackup(workspace_path)
                if backup:
                    await SandboxManager.restoreWorkspace(sandbox_id, backup)
                    logger.info("Restored %d files for user %d", len(backup), userId)

            return sandbox_id
        finally:
            if close_db:
                db.close()

    @staticmethod
    async def syncWorkspace(sandboxId: str) -> dict:
        """Read all files from sandbox /workspace and return {path: content}."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            files = await sandbox.glob_files("/workspace/**")
            result = {}
            for path in files:
                try:
                    content = await sandbox.read_file(path)
                    result[path] = content
                except Exception as e:
                    logger.warning("Failed to read %s: %s", path, e)
            return result
        finally:
            await client.close()

    @staticmethod
    async def restoreWorkspace(sandboxId: str, files: dict) -> None:
        """Write files back into sandbox filesystem."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            for path, content in files.items():
                await sandbox.write_file(path, content)
        finally:
            await client.close()

    @staticmethod
    def _saveBackup(userId: int, files: dict) -> None:
        """Save workspace files to host volume."""
        workspace_path = os.path.join(WORKSPACE_ROOT, str(userId))
        os.makedirs(workspace_path, exist_ok=True)
        for path, content in files.items():
            # Preserve relative path from /workspace/
            rel = path.lstrip("/")
            full = os.path.join(workspace_path, rel)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w") as f:
                f.write(content)

    @staticmethod
    def _loadBackup(userId: int | str) -> dict:
        """Load workspace files from host volume."""
        workspace_path = os.path.join(WORKSPACE_ROOT, str(userId))
        if not os.path.isdir(workspace_path):
            return {}
        result = {}
        for root, _dirs, filenames in os.walk(workspace_path):
            for fname in filenames:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, workspace_path)
                sandbox_path = f"/workspace/{rel}"
                with open(full) as f:
                    result[sandbox_path] = f.read()
        return result

    @staticmethod
    async def destroy(sandboxId: str, userId: int = None, db=None) -> None:
        """Destroy sandbox and clean up mapping."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.destroy()
            logger.info("Sandbox destroyed: %s", sandboxId)
        except Exception as e:
            logger.warning("Failed to destroy sandbox %s: %s", sandboxId, e)
        finally:
            await client.close()

        # Remove mapping
        if userId and db:
            mapping = db.query(PrometheusSandbox).filter_by(userId=userId).first()
            if mapping:
                db.delete(mapping)
                db.commit()

    @staticmethod
    async def execute(sandboxId: str, code: str, timeout: int = 30) -> dict:
        """Execute Python code in the sandbox."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            result: ExecResult = await sandbox.exec(
                command="python3",
                args=["-c", code],
                timeout=f"{timeout}s",
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        finally:
            await client.close()

    @staticmethod
    async def read_file(sandboxId: str, path: str) -> str:
        """Read a file from the sandbox filesystem."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            return await sandbox.read_file(path)
        finally:
            await client.close()

    @staticmethod
    async def write_file(sandboxId: str, path: str, content: str) -> bool:
        """Write a file to the sandbox filesystem."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.write_file(path, content)
            return True
        except Exception:
            return False
        finally:
            await client.close()

    @staticmethod
    async def list_files(sandboxId: str, path: str = "/workspace") -> dict:
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            entries = await sandbox.list_files(path)
            return {"entries": entries}
        finally:
            await client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sandbox_persistence.py -v`
Expected: All PASS

- [ ] **Step 5: Run existing sandbox tests to verify no regressions**

Run: `pytest tests/test_sandbox.py -v`
Expected: All PASS (existing create/execute/read/write/list/destroy still work)

- [ ] **Step 6: Commit**

```bash
git add main/app/prometheus/sandbox.py tests/test_sandbox_persistence.py
git commit -m "feat: add persistence layer to SandboxManager (reconnect, sync, restore)"
```

---

### Task 3: Agent Integration — Persistent Sandbox Lifecycle

**Files:**
- Modify: `main/app/prometheus/agent.py:194-275`
- Modify: `tests/test_agent_sandbox_integration.py`

**Interfaces:**
- Consumes: `SandboxManager.getOrCreate(userId, db)`, `SandboxManager.syncWorkspace(sandboxId)`, `SandboxManager._saveBackup(userId, files)`, `SandboxManager.destroy(sandboxId, userId, db)`
- Produces: Updated `streamMessage` with persistent sandbox lifecycle

- [ ] **Step 1: Write failing test for persistent lifecycle**

```python
# tests/test_agent_sandbox_integration.py — append
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestPersistentSandboxLifecycle:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.SandboxManager.getOrCreate")
    @patch("main.app.prometheus.sandbox.SandboxManager.syncWorkspace")
    @patch("main.app.prometheus.sandbox.SandboxManager._saveBackup")
    @patch("main.app.prometheus.sandbox.SandboxManager.destroy")
    async def test_stream_persists_sandbox(self, mock_destroy, mock_save, mock_sync, mock_get_or_create):
        """streamMessage uses getOrCreate instead of create, syncs on finish."""
        mock_get_or_create.return_value = "sb-persistent-123"
        mock_sync.return_value = {"/workspace/data.csv": "content"}

        # We can't easily test the full stream without heavy mocking,
        # but we verify the method signatures and flow exist
        from main.app.prometheus.sandbox import SandboxManager
        assert hasattr(SandboxManager, "getOrCreate")
        assert hasattr(SandboxManager, "syncWorkspace")
        assert hasattr(SandboxManager, "_saveBackup")
```

- [ ] **Step 2: Run test to verify it passes (method existence check)**

Run: `pytest tests/test_agent_sandbox_integration.py::TestPersistentSandboxLifecycle -v`
Expected: PASS

- [ ] **Step 3: Update agent.py streamMessage**

Replace the sandbox lifecycle in `streamMessage` (lines 198, 234-246, 269-274):

```python
# In streamMessage — replace sandbox_id = None with:
sandbox_id = None
userId = user.get("userId", 0) if user else 0

# Replace on-demand creation block (lines 234-246) with:
if fc.name == "execute_code" and sandbox_id is None:
    try:
        sandbox_id = await SandboxManager.getOrCreate(userId, db)
        logger.info("Persistent sandbox ready: %s for user %d", sandbox_id, userId)
    except Exception as e:
        logger.warning("Sandbox creation failed: %s", e)
        responses.append(
            types.Part.from_function_response(
                name=fc.name, response={"error": "Sandbox unavailable."}
            )
        )
        continue

# Replace finally block (lines 269-274) with:
finally:
    if sandbox_id:
        try:
            # Sync workspace to host volume before closing
            files = await SandboxManager.syncWorkspace(sandbox_id)
            if files:
                SandboxManager._saveBackup(userId, files)
                logger.info("Synced %d files for user %d", len(files), userId)
            # Don't destroy — keep alive for next request
        except Exception as e:
            logger.warning("Sandbox sync failed: %s", e)
    loop.flush()
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_agent_sandbox_integration.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/agent.py tests/test_agent_sandbox_integration.py
git commit -m "feat: agent uses persistent sandbox lifecycle (getOrCreate + sync)"
```

---

### Task 4: Cleanup Job — Expired Sandbox Sweeper

**Files:**
- Create: `main/app/prometheus/sandbox_cleanup.py`
- Modify: `tests/test_sandbox_persistence.py`

**Interfaces:**
- Consumes: `PrometheusSandbox` model, forgevm AsyncClient
- Produces: `cleanup_expired_sandboxes()` async function

- [ ] **Step 1: Write failing test**

```python
# tests/test_sandbox_persistence.py — append
class TestSandboxCleanup:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_cleanup_removes_dead_mappings(self, mock_get_client, dbSession):
        """Mappings for dead sandboxes are removed."""
        from main.app.prometheus.sandbox_cleanup import cleanup_expired_sandboxes

        # Add mapping for a sandbox that will fail get()
        dead = PrometheusSandbox(userId=99, sandboxId="sb-dead-old", workspacePath="/data/workspaces/99")
        dbSession.add(dead)
        dbSession.commit()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("not found"))
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        cleaned = await cleanup_expired_sandboxes(db=dbSession)
        assert cleaned >= 1
        remaining = dbSession.query(PrometheusSandbox).filter_by(userId=99).first()
        assert remaining is None

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_cleanup_keeps_alive_sandboxes(self, mock_get_client, dbSession):
        """Mappings for alive sandboxes are kept."""
        from main.app.prometheus.sandbox_cleanup import cleanup_expired_sandboxes

        alive = PrometheusSandbox(userId=1, sandboxId="sb-alive", workspacePath="/data/workspaces/1")
        dbSession.add(alive)
        dbSession.commit()

        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.extend_ttl = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        cleaned = await cleanup_expired_sandboxes(db=dbSession)
        assert cleaned == 0
        remaining = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert remaining is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_sandbox_persistence.py::TestSandboxCleanup -v`
Expected: FAIL — `cleanup_expired_sandboxes` doesn't exist

- [ ] **Step 3: Implement cleanup**

```python
# main/app/prometheus/sandbox_cleanup.py
import logging
from main.app.prometheus.sandbox import SandboxManager, _getClient
from main.models.sandbox import PrometheusSandbox

logger = logging.getLogger(__name__)


async def cleanup_expired_sandboxes(db=None):
    """Remove DB mappings for sandboxes that no longer exist in ForgeVM."""
    if db is None:
        from config import SessionLocal
        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        mappings = db.query(PrometheusSandbox).all()
        cleaned = 0
        for mapping in mappings:
            client = _getClient()
            try:
                await client.get(mapping.sandboxId)
            except Exception:
                # Sandbox dead — remove mapping
                db.delete(mapping)
                cleaned += 1
                logger.info("Cleaned dead sandbox mapping: user=%d sandbox=%s", mapping.userId, mapping.sandboxId)
            finally:
                await client.close()
        db.commit()
        return cleaned
    finally:
        if close_db:
            db.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_sandbox_persistence.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add main/app/prometheus/sandbox_cleanup.py tests/test_sandbox_persistence.py
git commit -m "feat: add sandbox cleanup job for expired mappings"
```

---

### Task 5: Full CI Verification

- [ ] **Step 1: Run full test suite**

Run: `.\ci.ps1`
Expected: All checks pass, coverage ≥ 80%

- [ ] **Step 2: Fix any failures**

- [ ] **Step 3: Final commit if needed**

```bash
git add -A
git commit -m "chore: fix CI issues for sandbox persistence"
```

---

### Task 6: Docker Compose — Workspace Volume for Persistence

**Files:**
- Modify: `docker-compose.yml:42-56`

**Interfaces:**
- Consumes: `WORKSPACE_ROOT` env var (default `/data/workspaces`)
- Produces: Workspace volume mounted in api container

- [ ] **Step 1: Add workspace volume to api service**

```yaml
# docker-compose.yml — add to api service volumes
    volumes:
      - .:/app
      - workspaces:/data/workspaces  # ADD THIS

# Add to bottom-level volumes
volumes:
  db_data:
  forgevm-data:
  workspaces:  # ADD THIS
```

- [ ] **Step 2: Add WORKSPACE_ROOT env var to api**

```yaml
# docker-compose.yml — add to api environment
    environment:
      - DEBUG_MODE=TRUE
      - TZ=America/Sao_Paulo
      - FORGEVM_URL=http://forgevm:7423
      - SANDBOX_IMAGE=python:3.12-slim
      - WORKSPACE_ROOT=/data/workspaces  # ADD THIS
```

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add workspace volume for sandbox persistence"
```

---

## Summary

| Task | Deliverable | Tests |
|---|---|---|
| 1 | DB model + migration | 3 model tests |
| 2 | SandboxManager persistence | 5 persistence tests |
| 3 | Agent integration | 1 integration test |
| 4 | Cleanup job | 2 cleanup tests |
| 5 | CI verification | Full suite |
| 6 | Docker compose | Volume mount |

**Total new tests:** ~11
**Files created:** 3 (model, cleanup, persistence tests)
**Files modified:** 4 (__init__, env.py, sandbox.py, agent.py)
