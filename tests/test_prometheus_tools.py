import inspect
import pytest
from main.app.prometheus.tools import (
    search_memory,
    save_memory,
    MEMORY_TOOLS,
    MEMORY_TOOL_NAMES,
    executeMemoryTool,
    dispatchToolCall,
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
        assert isinstance(MEMORY_TOOLS, list)
        assert len(MEMORY_TOOLS) == 2
        for tool in MEMORY_TOOLS:
            assert callable(tool)

    def test_memory_tool_names_unchanged(self):
        assert MEMORY_TOOL_NAMES == {"search_memory", "save_memory"}
