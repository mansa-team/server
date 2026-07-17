import inspect
import pytest
from main.app.prometheus.tools import (
    search_memory,
    save_memory,
    TOOL_REGISTRY,
)


class TestMemoryToolFunctions:
    def test_search_memory_has_docstring(self):
        assert search_memory.__doc__ is not None
        assert len(search_memory.__doc__) > 20

    def test_save_memory_has_docstring(self):
        assert save_memory.__doc__ is not None
        assert len(save_memory.__doc__) > 20

    def test_search_memory_signature(self):
        sig = inspect.signature(search_memory)
        params = list(sig.parameters.keys())
        assert "query" in params
        assert "limit" in params

    def test_save_memory_signature(self):
        sig = inspect.signature(save_memory)
        params = list(sig.parameters.keys())
        assert "key" in params
        assert "value" in params
        assert "type" in params

    def test_search_memory_has_type_hints(self):
        hints = inspect.get_annotations(search_memory)
        assert "query" in hints
        assert hints["query"] is str

    def test_save_memory_has_type_hints(self):
        hints = inspect.get_annotations(save_memory)
        assert "key" in hints
        assert "value" in hints
        assert "type" in hints

    def test_memory_tools_is_list_of_callables(self):
        assert isinstance(TOOL_REGISTRY, dict)
        assert len(TOOL_REGISTRY) >= 4
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn)

    def test_memory_tool_names_unchanged(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))


class TestToolRegistry:
    def test_registry_contains_memory_tools(self):
        assert "search_memory" in TOOL_REGISTRY
        assert "save_memory" in TOOL_REGISTRY

    def test_registry_values_are_callable(self):
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"

    def test_registry_matches_tool_names(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))
