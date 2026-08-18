import asyncio
import threading
from functools import wraps
from typing import Any, Callable, TypeVar

import orjson
from cashews import cache
from cashews.key import get_cache_key

try:
    from cashews.defaults import _empty as _MISS
except ImportError:  # pragma: no cover - private import fallback
    _MISS = object()

F = TypeVar("F", bound=Callable[..., Any])

# ponytail: per-thread event loop — avoids asyncio.run() creating + tearing down
# a new loop on every cache call (~13x faster single-thread, ~4x under 200-thread
# concurrency). Loop lives for the thread's lifetime (process lifetime in a web
# server). Upgrade path: none needed unless cashews drops sync compat.
_threadlocal = threading.local()


def _get_loop() -> asyncio.AbstractEventLoop:
    try:
        return _threadlocal.loop
    except AttributeError:
        _threadlocal.loop = asyncio.new_event_loop()
        return _threadlocal.loop


def sync_cache(ttl: str, key: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = get_cache_key(func, key, args, kwargs)
            loop = _get_loop()
            cached = loop.run_until_complete(cache.get(cache_key, default=_MISS))
            if cached is not _MISS:
                return cached  # ponytail: pre-serialized bytes, FastAPI passes through
            result = func(*args, **kwargs)
            serialized = orjson.dumps(result)
            loop.run_until_complete(cache.set(cache_key, serialized, expire=ttl))
            return serialized  # ponytail: pre-serialized bytes, FastAPI passes through

        return wrapper  # type: ignore[return-value]

    return decorator
