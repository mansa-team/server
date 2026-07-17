"""Tests for ResultCache."""

import json

import pytest

from main.app.prometheus.cache import ResultCache


@pytest.fixture
def cache(tmp_path):
    return ResultCache(str(tmp_path))


class TestResultCache:
    def test_set_and_get(self, cache):
        cache.set(1, "s1", "x = 1", {"value": 1})
        result = cache.get(1, "s1", "x = 1")
        assert result is not None
        assert result["result"] == {"value": 1}
        assert result["codeHash"]
        assert result["timestamp"] > 0

    def test_get_miss(self, cache):
        assert cache.get(1, "s1", "x = 1") is None

    def test_exists(self, cache):
        assert not cache.exists(1, "s1", "x = 1")
        cache.set(1, "s1", "x = 1", {"value": 1})
        assert cache.exists(1, "s1", "x = 1")

    def test_different_codes_different_hashes(self, cache):
        cache.set(1, "s1", "x = 1", {"a": 1})
        cache.set(1, "s1", "x = 2", {"a": 2})
        assert cache.get(1, "s1", "x = 1")["result"] == {"a": 1}
        assert cache.get(1, "s1", "x = 2")["result"] == {"a": 2}

    def test_invalidate(self, cache):
        cache.set(1, "s1", "x = 1", {"a": 1})
        cache.set(1, "s1", "x = 2", {"a": 2})
        cache.invalidate(1, "s1")
        assert cache.get(1, "s1", "x = 1") is None
        assert cache.get(1, "s1", "x = 2") is None

    def test_invalidate_does_not_affect_other_sessions(self, cache):
        cache.set(1, "s1", "x = 1", {"a": 1})
        cache.set(1, "s2", "x = 1", {"a": 2})
        cache.invalidate(1, "s1")
        assert cache.get(1, "s1", "x = 1") is None
        assert cache.get(1, "s2", "x = 1") is not None

    def test_invalidate_does_not_affect_other_users(self, cache):
        cache.set(1, "s1", "x = 1", {"a": 1})
        cache.set(2, "s1", "x = 1", {"a": 2})
        cache.invalidate(1, "s1")
        assert cache.get(1, "s1", "x = 1") is None
        assert cache.get(2, "s1", "x = 1") is not None

    def test_set_creates_directories(self, cache, tmp_path):
        cache.set(42, "sess-abc", "print(1)", {"out": "1"})
        expected = tmp_path / "42" / "sess-abc" / "computed"
        assert expected.exists()
        files = list(expected.glob("*.json"))
        assert len(files) == 1

    def test_overwrite_same_code(self, cache):
        cache.set(1, "s1", "x = 1", {"v": 1})
        cache.set(1, "s1", "x = 1", {"v": 2})
        result = cache.get(1, "s1", "x = 1")
        assert result["result"] == {"v": 2}

    def test_invalidate_empty_session(self, cache):
        # Should not raise
        cache.invalidate(999, "nonexistent")

    def test_json_roundtrip(self, cache):
        data = {"nested": {"list": [1, 2, 3], "str": "hello"}}
        cache.set(1, "s1", "code", data)
        result = cache.get(1, "s1", "code")
        assert result["result"] == data
