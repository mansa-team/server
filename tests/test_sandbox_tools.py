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
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id="sb-123")
        assert result["stdout"] == "42\n"
        mock_sandbox.execute.assert_called_once_with("sb-123", "print(42)", timeout=10)

    @pytest.mark.anyio
    async def test_dispatch_execute_code_no_sandbox(self):
        mock_fc = MagicMock()
        mock_fc.name = "execute_code"
        mock_fc.args = {"code": "print(42)"}
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id=None)
        assert "error" in result

    @pytest.mark.anyio
    @patch("main.app.prometheus.tools.SandboxManager")
    async def test_dispatch_read_file(self, mock_sandbox):
        mock_fc = MagicMock()
        mock_fc.name = "read_file"
        mock_fc.args = {"path": "/workspace/results.json"}
        mock_sandbox.read_file = AsyncMock(return_value='{"key": "value"}')
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id="sb-123")
        assert result["content"] == '{"key": "value"}'

    @pytest.mark.anyio
    @patch("main.app.prometheus.tools.SandboxManager")
    async def test_dispatch_write_file(self, mock_sandbox):
        mock_fc = MagicMock()
        mock_fc.name = "write_file"
        mock_fc.args = {"path": "/workspace/test.py", "content": "print(1)"}
        mock_sandbox.write_file = AsyncMock(return_value=True)
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id="sb-123")
        assert result["success"] is True

    @pytest.mark.anyio
    @patch("main.app.prometheus.tools.SandboxManager")
    async def test_dispatch_list_files(self, mock_sandbox):
        mock_fc = MagicMock()
        mock_fc.name = "list_files"
        mock_fc.args = {"path": "/workspace"}
        mock_sandbox.list_files = AsyncMock(return_value={"entries": [{"name": "a.py"}]})
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id="sb-123")
        assert len(result["entries"]) == 1

    @pytest.mark.anyio
    async def test_dispatch_read_file_no_sandbox(self):
        mock_fc = MagicMock()
        mock_fc.name = "read_file"
        mock_fc.args = {"path": "/workspace/data.csv"}
        result = await dispatchToolCall(mock_fc, {}, user={"userId": 1}, sandbox_id=None)
        assert "error" in result
