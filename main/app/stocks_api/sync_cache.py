import asyncio
import concurrent.futures
import inspect
import threading
from functools import wraps
from typing import Any, Callable, TypeVar

import cashews
from cashews.key import get_cache_key

MISS = object()

F = TypeVar("F", bound=Callable[..., Any])

SINGLEFLIGHT_TIMEOUT = 30.0

flightLock = threading.Lock()
flights: dict[str, threading.Event] = {}


def syncCacheGet(cacheKey: str) -> Any:
    async def getCall() -> Any:
        return await cashews.cache.get(cacheKey, default=MISS)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(getCall())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(getCall())).result()


def syncCacheSet(cacheKey: str, value: Any, ttl: str) -> None:
    async def setCall() -> None:
        await cashews.cache.set(cacheKey, value, expire=ttl)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(setCall())
        return
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: asyncio.run(setCall())).result()


def runAwaitable(awaitable: Any) -> Any:
    async def awaitCall() -> Any:
        return await awaitable

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitCall())
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(awaitCall())).result()


def cache(ttl: str, key: str) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cacheKey = get_cache_key(func, key, args, kwargs)

            def fetchAndStore() -> Any:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = runAwaitable(result)
                syncCacheSet(cacheKey, result, ttl)
                return result

            cached = syncCacheGet(cacheKey)
            if cached is not MISS:
                return cached
            with flightLock:
                flight = flights.get(cacheKey)
                if flight is None:
                    flight = threading.Event()
                    flights[cacheKey] = flight
                    owner = True
                else:
                    owner = False
            if not owner:
                flight.wait(timeout=SINGLEFLIGHT_TIMEOUT)
                # ponytail: waiter timeout falls through to a direct fetch, never blocks forever
                joined = syncCacheGet(cacheKey)
                return joined if joined is not MISS else fetchAndStore()
            filled = syncCacheGet(cacheKey)
            if filled is not MISS:
                with flightLock:
                    flights.pop(cacheKey, None)
                flight.set()
                return filled
            try:
                return fetchAndStore()
            finally:
                with flightLock:
                    flights.pop(cacheKey, None)
                flight.set()

        return wrapper  # type: ignore[return-value]

    return decorator


def clearEndpointCache() -> None:
    asyncio.run(cashews.cache.clear())
