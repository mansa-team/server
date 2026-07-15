"""
TDD tests: verify memory tools are wired into the Prometheus agent.

RED: These tests should fail if memory tools are not properly attached.
GREEN: All pass when wiring is correct.
"""

import pytest
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.prometheus.tools import MEMORY_TOOLS, MEMORY_TOOL_NAMES, executeMemoryTool, dispatchToolCall


class TestMemoryToolsDefinition:
    """MEMORY_TOOLS must be defined with the right function declarations."""

    def test_memory_tools_is_nonempty_list(self):
        assert isinstance(MEMORY_TOOLS, list)
        assert len(MEMORY_TOOLS) == 2

    def test_memory_tool_names_match(self):
        names = {t.name for t in MEMORY_TOOLS}
        assert names == {"search_memory", "save_memory"}

    def test_memory_tool_names_constant_matches(self):
        assert MEMORY_TOOL_NAMES == {"search_memory", "save_memory"}

    def test_search_memory_has_query_param(self):
        tool = next(t for t in MEMORY_TOOLS if t.name == "search_memory")
        props = tool.parameters.properties
        assert "query" in props
        assert tool.parameters.required == ["query"]

    def test_save_memory_has_required_params(self):
        tool = next(t for t in MEMORY_TOOLS if t.name == "save_memory")
        props = tool.parameters.properties
        assert "key" in props
        assert "value" in props
        assert "type" in props
        assert set(tool.parameters.required) == {"key", "value", "type"}


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

        tool_names = [t.name for t in tools_passed if hasattr(t, "name")]
        assert "search_memory" in tool_names, f"search_memory not in tools: {tool_names}"
        assert "save_memory" in tool_names, f"save_memory not in tools: {tool_names}"
        assert len(tools_passed) == 4, f"Expected 2 sessions + 2 memory tools, got {len(tools_passed)}"


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
        mock_client.session.call_tool = AsyncMock(return_value=MagicMock(isError=False, content=[MagicMock(text="28.50")]))

        with patch("main.app.prometheus.tools.executeMemoryTool", new_callable=AsyncMock) as mock_exec:
            result = await dispatchToolCall(mock_fc, {"stocks": mock_client}, user={"userId": 1})

        mock_exec.assert_not_called()
        assert "result" in result
