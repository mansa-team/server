import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from main.models.sandbox import PrometheusSandbox
from main.app.prometheus.sandbox import SandboxManager


def _mock_forgevm(mock_cls):
    """Wire up mock forgevm AsyncClient that returns sandbox with all methods."""
    mock_client = AsyncMock()
    mock_sandbox = AsyncMock()
    mock_sandbox.id = "sb-mock-123"
    mock_sandbox.exec = AsyncMock(return_value=MagicMock(stdout="Hello\n", stderr=""))
    mock_sandbox.read_file = AsyncMock(return_value="file contents")
    mock_sandbox.write_file = AsyncMock()
    mock_sandbox.list_files = AsyncMock(return_value=[{"path": "/workspace/data.csv", "size": 100, "is_dir": False}])
    mock_sandbox.destroy = AsyncMock()
    mock_sandbox.extend_ttl = AsyncMock()
    mock_sandbox.glob_files = AsyncMock(return_value=[])
    mock_client.spawn = AsyncMock(return_value=mock_sandbox)
    mock_client.get = AsyncMock(return_value=mock_sandbox)
    mock_client.close = AsyncMock()
    mock_cls.return_value = mock_client
    return mock_client, mock_sandbox


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
        existing = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert existing is not None
        assert existing.sandboxId == "sb-a"


class TestSandboxPersistence:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_get_or_create_creates_new_when_no_existing(self, mock_get_client, dbSession):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        assert result == "sb-mock-123"
        mock_client.spawn.assert_called_once()
        # Verify mapping stored in DB
        mapping = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert mapping is not None
        assert mapping.sandboxId == "sb-mock-123"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_get_or_create_reuses_existing(self, mock_get_client, dbSession):
        # Pre-create a mapping
        existing = PrometheusSandbox(userId=1, sandboxId="sb-existing", workspacePath="/data/workspaces/1")
        dbSession.add(existing)
        dbSession.commit()

        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        # Sandbox alive → extend_ttl called, returns existing sandboxId
        mock_sandbox.extend_ttl.assert_called_once()
        assert result == "sb-existing"
        mock_client.spawn.assert_not_called()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_get_or_create_respawns_when_dead(self, mock_get_client, dbSession):
        # Pre-create a mapping for a dead sandbox
        existing = PrometheusSandbox(userId=1, sandboxId="sb-dead", workspacePath="/data/workspaces/1")
        dbSession.add(existing)
        dbSession.commit()

        # client.get raises → sandbox is dead
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("sandbox not found"))
        mock_sandbox = AsyncMock()
        mock_sandbox.id = "sb-new-456"
        mock_client.spawn = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        result = await SandboxManager.getOrCreate(userId=1, db=dbSession)
        assert result == "sb-new-456"
        mock_client.spawn.assert_called_once()
        # Verify mapping updated
        mapping = dbSession.query(PrometheusSandbox).filter_by(userId=1).first()
        assert mapping.sandboxId == "sb-new-456"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_sync_to_sandbox(self, mock_get_client, tmp_path):
        """syncToSandbox pushes host files into the sandbox."""
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)

        # Set up host workspace with files
        workspace = tmp_path / "1"
        workspace.mkdir()
        (workspace / "data.csv").write_text("csv data")
        (workspace / "main.py").write_text("print('hello')")

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", str(tmp_path)):
            count = await SandboxManager.syncToSandbox("sb-mock-123", userId=1)

        assert count == 2
        # Verify sandbox.write_file was called for each file
        assert mock_sandbox.write_file.call_count == 2

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_sync_from_sandbox(self, mock_get_client, tmp_path):
        """syncFromSandbox pulls sandbox files to host."""
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        mock_sandbox.glob_files = AsyncMock(return_value=["/workspace/data.csv", "/workspace/main.py"])

        def _read(p):
            return f"content of {p}"

        mock_sandbox.read_file = AsyncMock(side_effect=_read)

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", str(tmp_path)):
            count = await SandboxManager.syncFromSandbox("sb-mock-123", userId=1)

        assert count == 2
        workspace = tmp_path / "1"
        assert (workspace / "data.csv").read_text() == "content of /workspace/data.csv"
        assert (workspace / "main.py").read_text() == "content of /workspace/main.py"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_sync_to_sandbox_empty_workspace(self, mock_get_client, tmp_path):
        """syncToSandbox returns 0 when workspace is empty."""
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", str(tmp_path)):
            count = await SandboxManager.syncToSandbox("sb-mock-123", userId=99)

        assert count == 0


class TestSandboxCleanup:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox_cleanup.getClient")
    async def test_cleanup_removes_dead_mappings(self, mock_get_client, dbSession):
        """Mappings for dead sandboxes are removed."""
        from main.app.prometheus.sandbox_cleanup import cleanup_expired_sandboxes

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
    @patch("main.app.prometheus.sandbox_cleanup.getClient")
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
