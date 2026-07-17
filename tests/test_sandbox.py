import pytest
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
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_create_sandbox(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.create(userId=1)
        assert result == "sb-mock-123"
        mock_client.spawn.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_execute_code(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.execute("sb-mock-123", "print('Hello')")
        assert result["stdout"] == "Hello\n"
        assert result["stderr"] == ""
        mock_sandbox.exec.assert_called_once_with(command="python3", args=["-c", "print('Hello')"], timeout="30s")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_read_file(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.read_file("sb-mock-123", "/workspace/data.csv")
        assert result == "file contents"
        mock_sandbox.read_file.assert_called_once_with("/workspace/data.csv")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_write_file(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.write_file("sb-mock-123", "/workspace/test.py", "print(42)")
        assert result is True
        mock_sandbox.write_file.assert_called_once_with("/workspace/test.py", "print(42)")

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_list_files(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        result = await SandboxManager.list_files("sb-mock-123", "/workspace")
        assert len(result["entries"]) == 1

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_destroy_sandbox(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        await SandboxManager.destroy("sb-mock-123")
        mock_sandbox.destroy.assert_called_once()

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
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
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_execute_passes_timeout(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        await SandboxManager.execute("sb-mock-123", "import time; time.sleep(99)", timeout=10)
        mock_sandbox.exec.assert_called_once_with(
            command="python3", args=["-c", "import time; time.sleep(99)"], timeout="10s"
        )

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_create_returns_sandbox_id(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        mock_sandbox.id = "sb-custom-id"
        result = await SandboxManager.create(userId=42)
        assert result == "sb-custom-id"

    @pytest.mark.asyncio
    @patch("main.app.prometheus.sandbox._getClient")
    async def test_write_file_returns_false_on_error(self, mock_get_client):
        mock_client, mock_sandbox = _mock_forgevm(mock_get_client)
        mock_sandbox.write_file.side_effect = Exception("write failed")
        result = await SandboxManager.write_file("sb-mock-123", "/workspace/f.txt", "data")
        assert result is False
