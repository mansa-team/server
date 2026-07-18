import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
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
    mock_client.spawn = AsyncMock(return_value=mock_sandbox)
    mock_client.get = AsyncMock(return_value=mock_sandbox)
    mock_client.close = AsyncMock()
    mock_cls.return_value = mock_client
    return mock_client, mock_sandbox


class TestSandboxManager:
    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_create_sandbox(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.create(userId=1)
        assert result == "sb-mock-123"
        mock_client.spawn.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_execute_code(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.execute(userId=1, code="print('Hello')", sandboxId="sb-mock-123")
        assert result["stdout"] == "Hello\n"
        assert result["stderr"] == ""
        mock_sandbox.exec.assert_called_once_with(command="python3", args=["-c", "print('Hello')"], timeout="30s")

    def test_read_file(self, tmp_path):
        """read_file reads from host filesystem."""
        workspace = tmp_path / "1"
        workspace.mkdir()
        (workspace / "data.csv").write_text("file contents")

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            result = SandboxManager.read_file(userId=1, path="/workspace/data.csv")
        assert result == "file contents"

    def test_write_file(self, tmp_path):
        """write_file writes to host filesystem."""
        workspace = tmp_path / "1"
        workspace.mkdir()

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            result = SandboxManager.write_file(userId=1, path="/workspace/test.py", content="print(42)")
        assert result is True
        assert (workspace / "test.py").read_text() == "print(42)"

    def test_list_files(self, tmp_path):
        """list_files lists host filesystem entries."""
        # hostPath(1, "/workspace") maps to WORKSPACE_ROOT/1/workspace/
        workspace = tmp_path / "1" / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "data.csv").write_text("x")

        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            result = SandboxManager.list_files(userId=1, path="/workspace")
        assert len(result["entries"]) == 1
        assert result["entries"][0].endswith("data.csv")

    def test_list_files_empty(self, tmp_path):
        """list_files returns empty for missing directory."""
        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            result = SandboxManager.list_files(userId=1, path="/workspace")
        assert result == {"entries": []}

    def test_read_file_not_found(self, tmp_path):
        """read_file raises FileNotFoundError for missing file."""
        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            with pytest.raises(FileNotFoundError):
                SandboxManager.read_file(userId=1, path="/workspace/nope.txt")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_destroy_sandbox(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        await SandboxManager.destroy("sb-mock-123")
        mock_sandbox.destroy.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_destroy_handles_failure(self, mock_get_client):
        mock_client = AsyncMock()
        mock_sandbox = AsyncMock()
        mock_sandbox.destroy.side_effect = Exception("connection refused")
        mock_client.get = AsyncMock(return_value=mock_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client
        # Should not raise
        await SandboxManager.destroy("sb-mock-123")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_execute_passes_timeout(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        await SandboxManager.execute(userId=1, code="import time; time.sleep(99)", sandboxId="sb-mock-123", timeout=10)
        mock_sandbox.exec.assert_called_once_with(
            command="python3", args=["-c", "import time; time.sleep(99)"], timeout="10s"
        )

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_create_returns_sandbox_id(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        mock_sandbox.id = "sb-custom-id"
        result = await SandboxManager.create(userId=42)
        assert result == "sb-custom-id"

    def test_write_file_returns_false_on_error(self, tmp_path):
        """write_file returns False when host write fails (e.g. invalid path chars)."""
        # Use a path with invalid characters to trigger an OS error
        with patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", tmp_path):
            result = SandboxManager.write_file(userId=1, path="/workspace/\x00bad.txt", content="data")
        assert result is False

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox.getClient")
    async def test_execute_retries_on_sandbox_not_found(self, mock_get_client):
        """execute() catches SandboxNotFound from exec, calls getOrCreate, retries."""
        from forgevm.exceptions import SandboxNotFound

        # First attempt: exec raises SandboxNotFound
        # getOrCreate creates new sandbox
        # Retry: exec succeeds
        dead_sandbox = AsyncMock()
        dead_sandbox.id = "sb-dead"
        dead_sandbox.exec = AsyncMock(side_effect=SandboxNotFound("dead"))

        new_sandbox = AsyncMock()
        new_sandbox.id = "sb-new-789"
        new_sandbox.exec = AsyncMock(return_value=MagicMock(stdout="retry ok\n", stderr=""))
        new_sandbox.glob_files = AsyncMock(return_value=[])

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=[
                dead_sandbox,  # execute() first attempt
                new_sandbox,  # getOrCreate health check (syncToSandbox calls client.get too)
                new_sandbox,  # syncToSandbox
                new_sandbox,  # execute() retry
            ]
        )
        mock_client.spawn = AsyncMock(return_value=new_sandbox)
        mock_client.close = AsyncMock()
        mock_get_client.return_value = mock_client

        # Mock SessionLocal so execute() retry doesn't hit real MySQL
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        with (
            patch("main.app.prometheus.sandbox.WORKSPACE_ROOT", Path("/tmp/ws")),
            patch("main.app.prometheus.sandbox.SessionLocal", return_value=mock_db),
        ):
            result = await SandboxManager.execute(userId=1, code="print('retry ok')", sandboxId="sb-dead")

        assert result["stdout"] == "retry ok\n"
        mock_client.spawn.assert_called_once()  # new sandbox created
