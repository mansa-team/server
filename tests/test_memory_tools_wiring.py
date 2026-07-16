"""
TDD tests: verify memory tools are wired into the Prometheus agent.

RED: These tests should fail if memory tools are not properly attached.
GREEN: All pass when wiring is correct.
"""

import inspect

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.prometheus.tools import MEMORY_TOOLS, MEMORY_TOOL_NAMES, executeMemoryTool, dispatchToolCall, search_memory, save_memory


class TestMemoryToolsDefinition:
    """MEMORY_TOOLS must be a list of callables with proper signatures."""

    def test_memory_tools_is_nonempty_list(self):
        assert isinstance(MEMORY_TOOLS, list)
        assert len(MEMORY_TOOLS) == 2  # two functions, SDK auto-generates declarations

    def test_memory_tools_are_callables(self):
        for tool in MEMORY_TOOLS:
            assert callable(tool)

    def test_memory_tool_names_match(self):
        names = {tool.__name__ for tool in MEMORY_TOOLS}
        assert names == {"search_memory", "save_memory"}

    def test_memory_tool_names_constant_matches(self):
        assert MEMORY_TOOL_NAMES == {"search_memory", "save_memory"}

    def test_search_memory_has_query_param(self):
        sig = inspect.signature(search_memory)
        params = list(sig.parameters.keys())
        assert "query" in params

    def test_save_memory_has_required_params(self):
        sig = inspect.signature(save_memory)
        params = list(sig.parameters.keys())
        assert "key" in params
        assert "value" in params
        assert "type" in params


class TestMakeChatIncludesMemoryTools:
    """makeChat must include MEMORY_TOOLS alongside MCP sessions."""

    @patch("main.app.prometheus.agent.types")
    @patch("main.app.prometheus.agent.Config")
    @patch("main.app.prometheus.agent.genai")
    @patch("main.app.prometheus.agent.Client")
    def test_makeChat_tools_include_memory_tools(self, mock_mcp, mock_genai, mock_config, mock_types):
        mock_config.PROMETHEUS = {"GEMINI_API.KEY": "key", "SEARXNG_HOST": "localhost", "SEARXNG_PORT": 8888}
        mock_config.STOCKS_API = {"HOST": "localhost", "PORT": 3200}

        from main.app.prometheus.agent import Prometheus

        gen = Prometheus()
        mock_session1 = MagicMock()
        mock_session2 = MagicMock()

        gen.makeChat([mock_session1, mock_session2], [], system_prompt="test")

        config_call = mock_types.GenerateContentConfig.call_args
        tools_passed = config_call.kwargs.get("tools") or config_call[1].get("tools")

        # Collect all tool names — functions have __name__, Tool objects have function_declarations
        all_func_names = []
        for t in tools_passed:
            if hasattr(t, "function_declarations") and t.function_declarations:
                all_func_names.extend(fd.name for fd in t.function_declarations)
            elif hasattr(t, "__name__"):
                all_func_names.append(t.__name__)
            elif hasattr(t, "name"):
                all_func_names.append(t.name)

        assert "search_memory" in all_func_names, f"search_memory not in tools: {all_func_names}"
        assert "save_memory" in all_func_names, f"save_memory not in tools: {all_func_names}"
        assert len(tools_passed) == 4, f"Expected 2 sessions + 2 memory functions, got {len(tools_passed)}"


class TestDispatchRoutesMemoryTools:
    """dispatchToolCall must route memory tool names to executeMemoryTool."""

    @pytest.mark.anyio
    async def test_search_memory_routed_to_executeMemoryTool(self):
        mock_fc = MagicMock()
        mock_fc.name = "search_memory"
        mock_fc.args = {"query": "PETR4"}

        with patch("main.app.prometheus.tools.executeMemoryTool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"memories": []}
            result = await dispatchToolCall(mock_fc, {}, user={"userId": 1})

        mock_exec.assert_called_once_with("search_memory", {"query": "PETR4"}, {"userId": 1})
        assert result == {"memories": []}

    @pytest.mark.anyio
    async def test_save_memory_routed_to_executeMemoryTool(self):
        mock_fc = MagicMock()
        mock_fc.name = "save_memory"
        mock_fc.args = {"key": "ticker", "value": "PETR4", "type": "preference"}

        with patch("main.app.prometheus.tools.executeMemoryTool", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"status": "created", "memoryId": 1}
            result = await dispatchToolCall(mock_fc, {}, user={"userId": 1})

        mock_exec.assert_called_once_with(
            "save_memory",
            {"key": "ticker", "value": "PETR4", "type": "preference"},
            {"userId": 1},
        )
        assert result["status"] == "created"

    @pytest.mark.anyio
    async def test_memory_tool_skipped_without_user(self):
        mock_fc = MagicMock()
        mock_fc.name = "search_memory"
        mock_fc.args = {"query": "test"}

        result = await dispatchToolCall(mock_fc, {}, user=None)
        assert "error" in result

    @pytest.mark.anyio
    async def test_non_memory_tool_not_routed_to_executeMemoryTool(self):
        mock_fc = MagicMock()
        mock_fc.name = "get_stock_price"
        mock_fc.args = {"ticker": "PETR4"}

        mock_client = AsyncMock()
        mock_client.session.call_tool = AsyncMock(
            return_value=MagicMock(isError=False, content=[MagicMock(text="28.50")])
        )

        with patch("main.app.prometheus.tools.executeMemoryTool", new_callable=AsyncMock) as mock_exec:
            result = await dispatchToolCall(mock_fc, {"stocks": mock_client}, user={"userId": 1})

        mock_exec.assert_not_called()
        assert "result" in result
