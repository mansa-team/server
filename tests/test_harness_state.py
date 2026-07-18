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
        assert not state.hasChanged()
        state.set("key", "value")
        assert state.hasChanged()

    def test_has_changed_false_after_reset(self):
        state = HarnessState()
        state.set("key", "value")
        state.resetChanged()
        assert not state.hasChanged()

    def test_toDict_returns_copy(self):
        state = HarnessState()
        state.set("a", 1)
        d = state.toDict()
        d["b"] = 2
        assert state.get("b") is None  # original unchanged

    def test_toContext_empty_when_no_data(self):
        state = HarnessState()
        assert state.toContext() == ""

    def test_toContext_formats_entries(self):
        state = HarnessState()
        state.set("step", "3/5")
        state.set("petr4_pe", 5.2)
        ctx = state.toContext()
        assert "- step: 3/5" in ctx
        assert "- petr4_pe: 5.2" in ctx

    def test_clear_resets_all(self):
        state = HarnessState()
        state.set("key", "value")
        state.clear()
        assert state.get("key") is None
        assert state.toDict() == {}
