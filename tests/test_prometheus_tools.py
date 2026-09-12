import asyncio
import inspect
import pytest
from unittest.mock import patch, MagicMock
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


def assert_gemini_safe(fn):
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
        assert_gemini_safe(fn)


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


class TestServeFile:
    def test_serve_file_returns_markdown_link(self):
        from main.app.prometheus.tools import serve_file

        with patch("main.app.prometheus.tools.hostPath") as m_host:
            fake_path = MagicMock()
            fake_path.exists.return_value = True
            fake_path.is_file.return_value = True
            fake_path.name = "report.csv"
            m_host.return_value = fake_path

            result = asyncio.run(serve_file("/workspace/report.csv", userId=1))

        assert result["url"] == "/prometheus/workspace/download?path=/workspace/report.csv"
        assert result["markdown"] == "[report.csv](/prometheus/workspace/download?path=/workspace/report.csv)"

    def test_serve_file_missing_file_returns_error(self):
        from main.app.prometheus.tools import serve_file

        with patch("main.app.prometheus.tools.hostPath") as m_host:
            fake_path = MagicMock()
            fake_path.exists.return_value = False
            m_host.return_value = fake_path

            result = asyncio.run(serve_file("/workspace/ghost.csv", userId=1))

        assert "error" in result

    def test_serve_file_rejects_traversal(self):
        from main.app.prometheus.tools import serve_file

        with patch("main.app.prometheus.tools.hostPath", side_effect=ValueError("Invalid workspace path")):
            result = asyncio.run(serve_file("/workspace/../../etc/passwd", userId=1))

        assert "error" in result

    def test_serve_file_quotes_special_chars(self):
        from main.app.prometheus.tools import serve_file

        with patch("main.app.prometheus.tools.hostPath") as m_host:
            fake_path = MagicMock()
            fake_path.exists.return_value = True
            fake_path.is_file.return_value = True
            fake_path.name = "my file.csv"
            m_host.return_value = fake_path

            result = asyncio.run(serve_file("/workspace/my file.csv", userId=1))

        assert "my%20file.csv" in result["url"]


class TestServeFileGeminiSafe:
    def test_serve_file_signature_is_gemini_safe(self):
        from main.app.prometheus.tools import serve_file

        assert_gemini_safe(serve_file)

    def test_serve_file_registered(self):
        from main.app.prometheus.tools import TOOL_REGISTRY

        assert "serve_file" in TOOL_REGISTRY


class TestWorkspaceToolsTraversal:
    def test_read_file_rejects_traversal(self):
        from main.app.prometheus.tools import read_file

        with patch(
            "main.app.prometheus.tools.SandboxManager.read_file",
            side_effect=ValueError("bad path"),
        ):
            result = asyncio.run(read_file("/workspace/../../etc/passwd", userId=1))

        assert result["error"] == "Invalid workspace path"

    def test_write_file_rejects_traversal(self):
        from main.app.prometheus.tools import write_file

        with patch(
            "main.app.prometheus.tools.SandboxManager.write_file",
            side_effect=ValueError("bad path"),
        ):
            result = asyncio.run(write_file("/workspace/../../etc/evil", "x", userId=1))

        assert result["error"] == "Invalid workspace path"

    def test_list_files_rejects_traversal(self):
        from main.app.prometheus.tools import list_files

        with patch(
            "main.app.prometheus.tools.SandboxManager.list_files",
            side_effect=ValueError("bad path"),
        ):
            result = asyncio.run(list_files("/workspace/../../etc", userId=1))

        assert result["error"] == "Invalid workspace path"
