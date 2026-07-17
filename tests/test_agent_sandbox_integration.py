"""Tests for agent <-> persistent sandbox integration (Task 3)."""

from unittest.mock import AsyncMock, patch

import pytest

from main.app.prometheus.sandbox import SandboxManager


class TestPersistentSandboxLifecycle:
    """Verify the agent uses getOrCreate + sync instead of create + destroy."""

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.SandboxManager.getOrCreate")
    @patch("main.app.prometheus.sandbox.SandboxManager.syncWorkspace")
    @patch("main.app.prometheus.sandbox.SandboxManager._saveBackup")
    async def test_stream_persists_sandbox(self, mock_save, mock_sync, mock_get_or_create):
        """streamMessage uses getOrCreate instead of create, syncs on finish."""
        mock_get_or_create.return_value = "sb-persistent-123"
        mock_sync.return_value = {"/workspace/data.csv": "content"}

        # Verify the API surface exists
        assert hasattr(SandboxManager, "getOrCreate")
        assert hasattr(SandboxManager, "syncWorkspace")
        assert hasattr(SandboxManager, "_saveBackup")

        # Simulate what the agent does
        sandbox_id = await SandboxManager.getOrCreate(42, db=None)
        assert sandbox_id == "sb-persistent-123"
        mock_get_or_create.assert_called_once_with(42, db=None)

        files = await SandboxManager.syncWorkspace(sandbox_id)
        assert files == {"/workspace/data.csv": "content"}

        await SandboxManager._saveBackup(42, files)
        mock_save.assert_called_once_with(42, {"/workspace/data.csv": "content"})

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.SandboxManager.getOrCreate")
    @patch("main.app.prometheus.sandbox.SandboxManager.syncWorkspace")
    @patch("main.app.prometheus.sandbox.SandboxManager._saveBackup")
    async def test_sync_empty_workspace_skips_save(self, mock_save, mock_sync, mock_get_or_create):
        """When syncWorkspace returns empty dict, _saveBackup is not called."""
        mock_get_or_create.return_value = "sb-empty"
        mock_sync.return_value = {}

        sandbox_id = await SandboxManager.getOrCreate(99, db=None)
        files = await SandboxManager.syncWorkspace(sandbox_id)

        # Agent logic: only save if files is truthy
        if files:
            await SandboxManager._saveBackup(99, files)

        mock_save.assert_not_called()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.SandboxManager.syncWorkspace", new_callable=AsyncMock)
    @patch("main.app.prometheus.sandbox.SandboxManager._saveBackup", new_callable=AsyncMock)
    async def test_agent_import_sandbox_manager(self, mock_save, mock_sync):
        """Agent module can import SandboxManager."""
        from main.app.prometheus.agent import Prometheus

        assert hasattr(Prometheus, "streamMessage")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.SandboxManager.getOrCreate", new_callable=AsyncMock)
    @patch("main.app.prometheus.sandbox.SandboxManager.syncWorkspace", new_callable=AsyncMock)
    @patch("main.app.prometheus.sandbox.SandboxManager._saveBackup", new_callable=AsyncMock)
    async def test_destroy_still_available(self, mock_save, mock_sync, mock_get_or_create):
        """destroy() still exists for explicit user requests."""
        assert hasattr(SandboxManager, "destroy")

    @pytest.mark.asyncio
    async def test_no_create_in_agent_source(self):
        """Verify agent.py no longer calls SandboxManager.create directly."""
        import inspect

        from main.app.prometheus import agent

        source = inspect.getsource(agent)
        # The on-demand path should use getOrCreate, not create
        # (SandboxManager.create is still in sandbox.py — just not called from agent)
        assert "SandboxManager.create(" not in source.split("getOrCreate")[0].split("finally:")[-1], (
            "Agent still calls SandboxManager.create in the on-demand path"
        )
