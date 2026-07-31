import asyncio
import inspect
import pytest
from main.app.prometheus.tools import (
    search_memory,
    save_memory,
    TOOL_REGISTRY,
)


# --- Gemini auto-function-calling compatibility ---
# Gemini introspects function signatures to build JSON schemas.
# Complex types (custom classes, Optional[Obj]) cause parse errors.
# All injected deps (state, user) must go in **_.

GEMINI_SAFE_TYPES = (str, int, float, bool, list, dict, type(None))


def _assert_gemini_safe(fn):
    """Assert a tool function has only Gemini-compatible parameter types."""
    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        if name.startswith("_") or param.kind == inspect.Parameter.VAR_KEYWORD:
            continue  # **_ or **kwargs — not exposed to Gemini
        if param.annotation is inspect.Parameter.empty:
            continue  # no annotation = safe
        # Allow simple types, unions of simple types, and Optional[simple]
        ann = param.annotation
        origin = getattr(ann, "__origin__", None)
        if origin is not None:
            # typing.Union, typing.Optional, etc — check inner args
            args = getattr(ann, "__args__", ())
            for a in args:
                assert a in GEMINI_SAFE_TYPES or a is type(None), f"{fn.__name__}({name}): type {a!r} not Gemini-safe"
        else:
            assert ann in GEMINI_SAFE_TYPES, f"{fn.__name__}({name}): type {ann!r} not Gemini-safe"


# --- Memory tool tests ---


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
        assert len(TOOL_REGISTRY) >= 2
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn)

    def test_memory_tool_names_unchanged(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))


# --- Gemini compatibility for ALL tools ---


class TestGeminiCompatibility:
    """Every function in TOOL_REGISTRY must have Gemini-safe signatures.
    Custom classes must NOT appear in parameter types —
    they go in **_ and are injected by dispatchToolCall."""

    @pytest.mark.parametrize("name,fn", list(TOOL_REGISTRY.items()))
    def test_tool_has_gemini_safe_signature(self, name, fn):
        _assert_gemini_safe(fn)


# --- Registry tests ---


class TestToolRegistry:
    def test_registry_contains_memory_tools(self):
        assert "search_memory" in TOOL_REGISTRY
        assert "save_memory" in TOOL_REGISTRY

    def test_registry_values_are_callable(self):
        for name, fn in TOOL_REGISTRY.items():
            assert callable(fn), f"{name} is not callable"

    def test_registry_matches_tool_names(self):
        assert {"search_memory", "save_memory"}.issubset(set(TOOL_REGISTRY.keys()))
