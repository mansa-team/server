import time
from main.app.stocks_api.response_cache import ResponseCache


class TestResponseCache:
    def test_miss(self):
        c = ResponseCache()
        assert c.get("nonexistent") is None

    def test_hit(self):
        c = ResponseCache()
        c.set("key1", {"data": "value"})
        assert c.get("key1") == {"data": "value"}

    def test_expiry(self):
        c = ResponseCache(defaultTTL=0)
        c.set("key1", {"data": "value"})
        assert c.get("key1") is None

    def test_lru_eviction(self):
        c = ResponseCache(maxSize=2)
        c.set("a", {"r": 1})
        c.set("b", {"r": 2})
        c.set("c", {"r": 3})
        assert c.get("a") is None
        assert c.get("b") == {"r": 2}
        assert c.get("c") == {"r": 3}

    def test_make_key(self):
        c = ResponseCache()
        k1 = c.makeKey("historical", search="PETR4", fields="P/L")
        k2 = c.makeKey("historical", search="PETR4", fields="P/L")
        k3 = c.makeKey("historical", search="VALE3", fields="P/L")
        assert k1 == k2
        assert k1 != k3

    def test_ttl_per_endpoint(self):
        c = ResponseCache(ttlMap={"live": 0, "cotations": 300})
        c.set("live:PETR4", {"price": 28.5})
        assert c.get("live:PETR4") is None
