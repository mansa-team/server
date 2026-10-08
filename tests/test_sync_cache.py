import asyncio
from typing import Any

import orjson
import pytest
import pytest_asyncio

from cashews import cache as cashewsCache

from main.utils.sync_cache import MISS, clearEndpointCache, sync_cache, syncCacheGet, syncCacheSet


@pytest_asyncio.fixture(scope="module", loop_scope="module", autouse=True)
async def setup_cache():
    cashewsCache.setup("mem://")
    yield
    await cashewsCache.clear()


def test_hit_returns_cached_value_without_calling_func():
    calls = []

    @sync_cache(ttl="1h", key="test:simple:{x}")
    def fn(x):
        calls.append(x)
        return orjson.dumps({"x": x})

    first = fn(x=1)
    second = fn(x=1)

    assert first == second == orjson.dumps({"x": 1})
    assert calls == [1]  # computed once, second call is a cache hit


def test_distinct_args_get_distinct_cache_entries():
    calls = []

    @sync_cache(ttl="1h", key="test:distinct:{x}")
    def fn(x):
        calls.append(x)
        return orjson.dumps({"x": x})

    fn(x=1)
    fn(x=2)

    assert calls == [1, 2]


def test_params_not_in_template_are_excluded_from_key():
    calls = []

    @sync_cache(ttl="1h", key="test:exclude:{x}")
    def fn(x, junk="ignored"):
        calls.append(x)
        return orjson.dumps({"x": x})

    fn(x=1, junk="a")
    fn(x=1, junk="b")  # junk must not change the key

    assert calls == [1]


def test_exceptions_propagate_and_are_not_cached():
    calls = []

    @sync_cache(ttl="1h", key="test:exc:{x}")
    def fn(x):
        calls.append(x)
        raise ValueError("boom")

    with pytest.raises(ValueError):
        fn(x=1)
    with pytest.raises(ValueError):
        fn(x=1)  # must re-raise, not return a cached exception

    assert calls == [1, 1]


class LoopBindingStub:
    """Fake backend mimicking redis.asyncio transport loop-binding.

    The first event loop to touch it wins; any later loop raises the same
    RuntimeError the redis dev stack 500ed with. mem:// never binds, which is
    why per-call asyncio.run stayed green in CI while redis broke live.
    """

    def __init__(self) -> None:
        self.store: dict[str, Any] = {}
        self.boundLoop: asyncio.AbstractEventLoop | None = None

    def pin(self) -> None:
        loop = asyncio.get_running_loop()
        if self.boundLoop is None:
            self.boundLoop = loop
        elif loop is not self.boundLoop:
            raise RuntimeError("Event loop is closed")

    async def get(self, key: str, default: Any = None) -> Any:
        self.pin()
        return self.store.get(key, default)

    async def set(self, key: str, value: Any, expire: Any = None, **kwargs: Any) -> bool:
        self.pin()
        self.store[key] = value
        return True

    async def delete_match(self, pattern: str) -> None:
        self.pin()
        prefix = pattern.split("*")[0]
        for key in [k for k in self.store if k.startswith(prefix)]:
            del self.store[key]


def test_per_call_loop_breaks_loop_bound_backend():
    stub = LoopBindingStub()
    asyncio.run(stub.set("k", "v"))
    with pytest.raises(RuntimeError, match="Event loop is closed"):
        asyncio.run(stub.get("k"))


def test_runOnCacheLoop_pins_all_cache_io_to_one_loop(monkeypatch: pytest.MonkeyPatch):
    stub = LoopBindingStub()
    monkeypatch.setattr("main.utils.sync_cache.cache", stub)
    syncCacheSet("loop:a", "1", "1h")
    assert syncCacheGet("loop:a") == "1"
    syncCacheSet("loop:b", "2", "1h")
    assert syncCacheGet("loop:b") == "2"
    assert stub.boundLoop is not None and stub.boundLoop.is_running()


async def test_runOnCacheLoop_called_with_running_loop(monkeypatch: pytest.MonkeyPatch):
    stub = LoopBindingStub()
    monkeypatch.setattr("main.utils.sync_cache.cache", stub)
    syncCacheSet("loop:c", "3", "1h")
    assert syncCacheGet("loop:c") == "3"
    assert stub.boundLoop is not None and stub.boundLoop is not asyncio.get_running_loop()


def test_decorator_caches_without_recompute_on_loop_bound_backend(monkeypatch: pytest.MonkeyPatch):
    stub = LoopBindingStub()
    monkeypatch.setattr("main.utils.sync_cache.cache", stub)
    calls = []

    @sync_cache(ttl="1h", key="test:pinned:{x}")
    def fn(x):
        calls.append(x)
        return {"x": x}

    assert fn(x=7) == {"x": 7}
    assert fn(x=7) == {"x": 7}
    assert calls == [7]


def test_clear_endpoint_cache_via_runner(monkeypatch: pytest.MonkeyPatch):
    stub = LoopBindingStub()
    monkeypatch.setattr("main.utils.sync_cache.cache", stub)
    syncCacheSet("stocks:t", "v", "1h")
    syncCacheSet("wallet:t", "v", "1h")
    clearEndpointCache()
    assert syncCacheGet("stocks:t") is MISS
    assert syncCacheGet("wallet:t") is MISS
