import inspect

import pytest

from main.app.prometheus.state import HarnessState
from main.app.prometheus.tools import (
    STATE_TOOL_NAMES,
    STATE_TOOLS,
    executeStateTool,
    get_state,
    set_state,
)


class TestStateToolFunctions:
    def test_get_state_has_docstring(self):
        assert get_state.__doc__ is not None
        assert len(get_state.__doc__) > 20

    def test_set_state_has_docstring(self):
        assert set_state.__doc__ is not None
        assert len(set_state.__doc__) > 20

    def test_get_state_signature(self):
        sig = inspect.signature(get_state)
        params = list(sig.parameters.keys())
        assert "key" in params

    def test_set_state_signature(self):
        sig = inspect.signature(set_state)
        params = list(sig.parameters.keys())
        assert "key" in params
        assert "value" in params

    def test_get_state_has_type_hints(self):
        hints = inspect.get_annotations(get_state)
        assert "key" in hints

    def test_set_state_has_type_hints(self):
        hints = inspect.get_annotations(set_state)
        assert "key" in hints
        assert "value" in hints

    def test_state_tools_is_list_of_callables(self):
        assert isinstance(STATE_TOOLS, list)
        assert len(STATE_TOOLS) == 2
        for tool in STATE_TOOLS:
            assert callable(tool)

    def test_state_tool_names(self):
        assert STATE_TOOL_NAMES == {"get_state", "set_state"}


class TestExecuteStateTool:
    @pytest.mark.anyio
    async def test_get_state_specific_key(self):
        state = HarnessState()
        state.set("petr4_pe", 5.2)
        result = await executeStateTool("get_state", {"key": "petr4_pe"}, state)
        assert result == {"petr4_pe": 5.2}

    @pytest.mark.anyio
    async def test_get_state_all(self):
        state = HarnessState()
        state.set("a", 1)
        state.set("b", 2)
        result = await executeStateTool("get_state", {}, state)
        assert result == {"a": 1, "b": 2}

    @pytest.mark.anyio
    async def test_get_state_missing_key(self):
        state = HarnessState()
        result = await executeStateTool("get_state", {"key": "missing"}, state)
        assert result == {"missing": None}

    @pytest.mark.anyio
    async def test_set_state(self):
        state = HarnessState()
        result = await executeStateTool("set_state", {"key": "step", "value": "3/5"}, state)
        assert result == {"status": "ok", "key": "step"}
        assert state.get("step") == "3/5"

    @pytest.mark.anyio
    async def test_unknown_tool(self):
        state = HarnessState()
        result = await executeStateTool("unknown_tool", {}, state)
        assert "error" in result
