"""
TDD tests: verify memory tools are wired into the Prometheus agent.

RED: These tests should fail if memory tools are not properly attached.
GREEN: All pass when wiring is correct.
"""

import inspect
import pytest
import sys
import os
from unittest.mock import patch, AsyncMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main.app.prometheus.tools import (
    TOOL_REGISTRY,
    search_memory,
    save_memory,
)


class TestMemoryToolFunctions:
    """Verify the actual async tool functions have correct signatures."""

    def test_search_memory_has_docstring(self):
        assert search_memory.__doc__ is not None
        assert len(search_memory.__doc__) > 10

    def test_save_memory_has_docstring(self):
        assert save_memory.__doc__ is not None
        assert len(save_memory.__doc__) > 10

    def test_search_memory_signature(self):
        sig = inspect.signature(search_memory)
        params = list(sig.parameters.keys())
        assert "query" in params

    def test_save_memory_signature(self):
        sig = inspect.signature(save_memory)
        params = list(sig.parameters.keys())
        assert "key" in params
        assert "value" in params
        assert "type" in params

    def test_search_memory_has_type_hints(self):
        hints = search_memory.__annotations__
        assert "return" in hints

    def test_save_memory_has_type_hints(self):
        hints = save_memory.__annotations__
        assert "return" in hints

    def test_memory_tools_is_list_of_callables(self):
        assert isinstance(TOOL_REGISTRY, dict)
        assert len(TOOL_REGISTRY) >= 4
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn)

    def test_memory_tool_names_unchanged(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))


class TestToolRegistry:
    """TOOL_REGISTRY pattern must work correctly."""

    def test_registry_contains_memory_tools(self):
        assert "search_memory" in TOOL_REGISTRY
        assert "save_memory" in TOOL_REGISTRY

    def test_registry_values_are_callable(self):
        for fn in TOOL_REGISTRY.values():
            assert callable(fn)

    def test_registry_matches_tool_names(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))


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
        mock_session1 = AsyncMock()
        mock_session2 = AsyncMock()

        gen.makeChat([mock_session1, mock_session2], [], system_prompt="test")

        config_call = mock_types.GenerateContentConfig.call_args
        tools_passed = config_call.kwargs.get("tools") or config_call[1].get("tools")

        all_func_names = []
        for t in tools_passed:
            if hasattr(t, "function_declarations") and t.function_declarations:
                all_func_names.extend(fd.name for fd in t.function_declarations)
            elif hasattr(t, "__name__"):
                all_func_names.append(t.__name__)

        assert "search_memory" in all_func_names, f"search_memory not in tools: {all_func_names}"
        assert "save_memory" in all_func_names, f"save_memory not in tools: {all_func_names}"


class TestDispatchRoutesMemoryTools:
    """dispatchToolCall must route memory tool names via TOOL_REGISTRY."""

    @pytest.mark.anyio
    async def test_search_memory_routed_via_registry(self):
        from main.app.prometheus.tools import dispatchToolCall

        mock_fc = AsyncMock()
        mock_fc.name = "search_memory"
        mock_fc.args = {"query": "PETR4"}

        mock_fn = AsyncMock(return_value={"memories": []})
        with patch.dict(TOOL_REGISTRY, {"search_memory": mock_fn}):
            result = await dispatchToolCall(mock_fc, {}, user={"userId": 1})

        mock_fn.assert_called_once_with(
            query="PETR4", user={"userId": 1}, state=None, db=None, sandbox_id=None, userId=1
        )
        assert result == {"memories": []}

    @pytest.mark.anyio
    async def test_save_memory_routed_via_registry(self):
        from main.app.prometheus.tools import dispatchToolCall

        mock_fc = AsyncMock()
        mock_fc.name = "save_memory"
        mock_fc.args = {"key": "ticker", "value": "PETR4", "type": "preference"}

        mock_fn = AsyncMock(return_value={"status": "created", "memoryId": 1})
        with patch.dict(TOOL_REGISTRY, {"save_memory": mock_fn}):
            result = await dispatchToolCall(mock_fc, {}, user={"userId": 1})

        mock_fn.assert_called_once_with(
            key="ticker",
            value="PETR4",
            type="preference",
            user={"userId": 1},
            state=None,
            db=None,
            sandbox_id=None,
            userId=1,
        )
        assert result["status"] == "created"

    @pytest.mark.anyio
    async def test_non_registry_tool_not_routed(self):
        from main.app.prometheus.tools import dispatchToolCall

        mock_fc = AsyncMock()
        mock_fc.name = "get_stock_price"
        mock_fc.args = {"ticker": "PETR4"}

        mock_client = AsyncMock()
        mock_client.session.call_tool = AsyncMock(
            return_value=AsyncMock(isError=False, content=[AsyncMock(text="28.50")])
        )

        result = await dispatchToolCall(mock_fc, {"stocks": mock_client}, user={"userId": 1})
        assert "result" in result
