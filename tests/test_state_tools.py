import inspect
from unittest.mock import MagicMock

import pytest

from main.app.prometheus.state import HarnessState
from main.app.prometheus.tools import (
    TOOL_REGISTRY,
    dispatchToolCall,
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
        assert "state" in params

    def test_set_state_signature(self):
        sig = inspect.signature(set_state)
        params = list(sig.parameters.keys())
        assert "key" in params
        assert "value" in params
        assert "state" in params

    def test_get_state_has_type_hints(self):
        hints = inspect.get_annotations(get_state)
        assert "key" in hints
        assert "state" in hints

    def test_set_state_has_type_hints(self):
        hints = inspect.get_annotations(set_state)
        assert "key" in hints
        assert "value" in hints
        assert "state" in hints

    def test_state_tools_in_registry(self):
        assert "get_state" in TOOL_REGISTRY
        assert "set_state" in TOOL_REGISTRY
        assert TOOL_REGISTRY["get_state"] is get_state
        assert TOOL_REGISTRY["set_state"] is set_state

    def test_registry_has_all_tools(self):
        assert len(TOOL_REGISTRY) == 4


class TestGetState:
    @pytest.mark.anyio
    async def test_get_state_specific_key(self):
        state = HarnessState()
        state.set("petr4_pe", 5.2)
        result = await get_state(key="petr4_pe", state=state)
        assert result == {"petr4_pe": 5.2}

    @pytest.mark.anyio
    async def test_get_state_all(self):
        state = HarnessState()
        state.set("a", 1)
        state.set("b", 2)
        result = await get_state(state=state)
        assert result == {"a": 1, "b": 2}

    @pytest.mark.anyio
    async def test_get_state_missing_key(self):
        state = HarnessState()
        result = await get_state(key="missing", state=state)
        assert result == {"missing": None}

    @pytest.mark.anyio
    async def test_get_state_no_state(self):
        result = await get_state(key="test")
        assert "error" in result


class TestSetState:
    @pytest.mark.anyio
    async def test_set_state(self):
        state = HarnessState()
        result = await set_state(key="step", value="3/5", state=state)
        assert result == {"status": "ok", "key": "step"}
        assert state.get("step") == "3/5"

    @pytest.mark.anyio
    async def test_set_state_no_state(self):
        result = await set_state(key="test", value="value")
        assert "error" in result


class TestStateDispatch:
    @pytest.mark.anyio
    async def test_dispatch_get_state(self):
        state = HarnessState()
        state.set("petr4_pe", 5.2)
        fc = MagicMock()
        fc.name = "get_state"
        fc.args = {"key": "petr4_pe"}
        result = await dispatchToolCall(fc, {}, state=state)
        assert result == {"petr4_pe": 5.2}

    @pytest.mark.anyio
    async def test_dispatch_set_state(self):
        state = HarnessState()
        fc = MagicMock()
        fc.name = "set_state"
        fc.args = {"key": "step", "value": "3/5"}
        result = await dispatchToolCall(fc, {}, state=state)
        assert result == {"status": "ok", "key": "step"}
        assert state.get("step") == "3/5"
