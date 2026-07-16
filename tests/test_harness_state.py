import pytest
from main.app.prometheus.state import HarnessState


class TestHarnessState:
    def test_get_returns_none_when_empty(self):
        state = HarnessState()
        assert state.get("missing") is None

    def test_get_returns_default_when_empty(self):
        state = HarnessState()
        assert state.get("missing", "fallback") == "fallback"

    def test_set_and_get(self):
        state = HarnessState()
        state.set("key", "value")
        assert state.get("key") == "value"

    def test_set_overwrites(self):
        state = HarnessState()
        state.set("key", "old")
        state.set("key", "new")
        assert state.get("key") == "new"

    def test_has_changed_true_after_set(self):
        state = HarnessState()
        assert not state.has_changed()
        state.set("key", "value")
        assert state.has_changed()

    def test_has_changed_false_after_reset(self):
        state = HarnessState()
        state.set("key", "value")
        state.reset_changed()
        assert not state.has_changed()

    def test_to_dict_returns_copy(self):
        state = HarnessState()
        state.set("a", 1)
        d = state.to_dict()
        d["b"] = 2
        assert state.get("b") is None  # original unchanged

    def test_to_context_empty_when_no_data(self):
        state = HarnessState()
        assert state.to_context() == ""

    def test_to_context_formats_entries(self):
        state = HarnessState()
        state.set("step", "3/5")
        state.set("petr4_pe", 5.2)
        ctx = state.to_context()
        assert "- step: 3/5" in ctx
        assert "- petr4_pe: 5.2" in ctx

    def test_clear_resets_all(self):
        state = HarnessState()
        state.set("key", "value")
        state.clear()
        assert state.get("key") is None
        assert state.to_dict() == {}
