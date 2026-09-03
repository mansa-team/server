import asyncio
import orjson
import pytest

from cashews import cache

from main.app.stocks_api.sync_cache import sync_cache


@pytest.fixture(scope="module", autouse=True)
def setup_cache():
    cache.setup("mem://")
    yield
    asyncio.run(cache.clear())


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
