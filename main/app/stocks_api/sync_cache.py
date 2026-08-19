import asyncio
from functools import wraps
from typing import Any, Callable, TypeVar

from cashews import cache
from cashews.key import get_cache_key

F = TypeVar("F", bound=Callable[..., Any])

cache.setup("mem://")


def sync_cache(
    ttl: str,
    key: str,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = get_cache_key(func, key, args, kwargs)

            loop = asyncio.new_event_loop()
            try:
                cached = loop.run_until_complete(cache.get(cache_key))
                if cached is not None:
                    return cached
            finally:
                loop.close()

            result = func(*args, **kwargs)

            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(cache.set(cache_key, result, expire=ttl))
            finally:
                loop.close()

            return result

        return wrapper  # type: ignore[return-value]

    return decorator
