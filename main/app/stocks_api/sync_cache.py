import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

from cashews import cache
from cashews.key import get_cache_key

try:
    from cashews.defaults import _empty as MISS
except ImportError:  # pragma: no cover - private import fallback
    MISS = object()

F = TypeVar("F", bound=Callable[..., Any])


def sync_cache(ttl: str, key: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = get_cache_key(func, key, args, kwargs)
            cached = asyncio.run(cache.get(cache_key, default=MISS))
            if cached is not MISS:
                return cached
            result = func(*args, **kwargs)
            asyncio.run(cache.set(cache_key, result, expire=ttl))
            return result

        return wrapper  # type: ignore[return-value]

    return decorator
