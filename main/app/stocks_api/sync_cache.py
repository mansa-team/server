import asyncio
import concurrent.futures
import inspect
from functools import wraps
from typing import Any, Callable, TypeVar

import cashews
from cashews.key import get_cache_key

MISS = object()

F = TypeVar("F", bound=Callable[..., Any])


def cache(ttl: str, key: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache_key = get_cache_key(func, key, args, kwargs)

            async def cachedCall() -> Any:
                cached = await cashews.cache.get(cache_key, default=MISS)
                if cached is not MISS:
                    return cached
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                await cashews.cache.set(cache_key, result, expire=ttl)
                return result

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return asyncio.run(cachedCall())
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(lambda: asyncio.run(cachedCall())).result()

        return wrapper  # type: ignore[return-value]

    return decorator


def clearEndpointCache() -> None:
    asyncio.run(cashews.cache.clear())
