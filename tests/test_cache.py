import time
from main.app.stocks_api.response_cache import ResponseCache


class TestCacheKey:
    def test_deterministic(self):
        c = ResponseCache()
        k1 = c.makeKey("cotations", search="PETR4")
        k2 = c.makeKey("cotations", search="PETR4")
        assert k1 == k2

    def test_different_args_different_key(self):
        c = ResponseCache()
        k1 = c.makeKey("cotations", search="PETR4")
        k2 = c.makeKey("cotations", search="VALE3")
        assert k1 != k2

    def test_different_tool_different_key(self):
        c = ResponseCache()
        k1 = c.makeKey("cotations", search="PETR4")
        k2 = c.makeKey("fundamental", search="PETR4")
        assert k1 != k2


class TestCacheGetSet:
    def test_miss(self):
        c = ResponseCache()
        key = c.makeKey("cotations", search="PETR4")
        assert c.get(key) is None

    def test_hit(self):
        c = ResponseCache()
        key = c.makeKey("cotations", search="PETR4")
        c.set(key, {"result": "data"})
        assert c.get(key) == {"result": "data"}

    def test_expiry(self):
        c = ResponseCache(defaultTTL=0)
        key = c.makeKey("cotations", search="PETR4")
        c.set(key, {"result": "data"})
        assert c.get(key) is None


class TestCacheEviction:
    def test_lru_eviction(self):
        c = ResponseCache(maxSize=2)
        k1 = c.makeKey("a", x=1)
        k2 = c.makeKey("b", x=2)
        k3 = c.makeKey("c", x=3)
        c.set(k1, {"r": 1})
        c.set(k2, {"r": 2})
        c.set(k3, {"r": 3})
        assert c.get(k1) is None
        assert c.get(k2) == {"r": 2}
        assert c.get(k3) == {"r": 3}
