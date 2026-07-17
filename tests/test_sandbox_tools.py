import inspect
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from main.app.prometheus.tools import TOOL_REGISTRY, dispatchToolCall
from main.app.prometheus.state import HarnessState


class TestSandboxToolDefinitions:
    def test_execute_code_in_registry(self):
        assert "execute_code" in TOOL_REGISTRY

    def test_read_sandbox_file_in_registry(self):
        assert "read_sandbox_file" in TOOL_REGISTRY

    def test_check_cache_in_registry(self):
        assert "check_cache" in TOOL_REGISTRY

    def test_execute_code_has_docstring(self):
        fn = TOOL_REGISTRY["execute_code"]
        assert fn.__doc__ is not None
        assert len(fn.__doc__) > 20

    def test_read_sandbox_file_has_docstring(self):
        fn = TOOL_REGISTRY["read_sandbox_file"]
        assert fn.__doc__ is not None
        assert len(fn.__doc__) > 20

    def test_check_cache_has_docstring(self):
        fn = TOOL_REGISTRY["check_cache"]
        assert fn.__doc__ is not None
        assert len(fn.__doc__) > 20


class TestCheckCache:
    @pytest.mark.anyio
    async def test_check_cache_hit(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = {"stdout": "42\n"}
        result = await TOOL_REGISTRY["check_cache"](code_hash="abc123", cache=mock_cache)
        assert result["hit"] is True
        assert result["result"]["stdout"] == "42\n"

    @pytest.mark.anyio
    async def test_check_cache_miss(self):
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        result = await TOOL_REGISTRY["check_cache"](code_hash="abc123", cache=mock_cache)
        assert result["hit"] is False

    @pytest.mark.anyio
    async def test_check_cache_no_cache(self):
        result = await TOOL_REGISTRY["check_cache"](code_hash="abc123", cache=None)
        assert "error" in result


class TestDispatchToolCallSandbox:
    @pytest.mark.anyio
    @patch("main.app.prometheus.tools.SandboxManager")
    async def test_dispatch_execute_code_routes_to_registry(self, mock_sandbox):
        mock_fc = MagicMock()
        mock_fc.name = "execute_code"
        mock_fc.args = {"code": "print(42)", "timeout": 10}
        mock_sandbox.execute = AsyncMock(return_value={"stdout": "42\n", "stderr": ""})
        mock_cache = MagicMock()
        mock_cache.compute_hash.return_value = "hash123"
        mock_cache.get.return_value = None
        state = HarnessState()
        result = await dispatchToolCall(
            mock_fc,
            {},
            user={"userId": 1},
            state=state,
            sandbox_id="sb-123",
            cache=mock_cache,
        )
        assert result["stdout"] == "42\n"
        mock_sandbox.execute.assert_called_once_with("sb-123", "print(42)", 10)

    @pytest.mark.anyio
    async def test_dispatch_execute_code_no_sandbox(self):
        mock_fc = MagicMock()
        mock_fc.name = "execute_code"
        mock_fc.args = {"code": "print(42)"}
        state = HarnessState()
        result = await dispatchToolCall(
            mock_fc,
            {},
            user={"userId": 1},
            state=state,
            sandbox_id=None,
            cache=None,
        )
        assert "error" in result
