import asyncio
import concurrent.futures
import inspect
import threading
from functools import wraps
from typing import Any, Callable, TypeVar

from cashews import cache
from cashews.key import get_cache_key

MISS = object()

F = TypeVar("F", bound=Callable[..., Any])

SINGLEFLIGHT_TIMEOUT = 30.0

flightLock = threading.Lock()
flights: dict[str, threading.Event] = {}

cacheLoopLock = threading.Lock()
cacheLoop: asyncio.AbstractEventLoop | None = None


def getCacheLoop() -> asyncio.AbstractEventLoop:
    global cacheLoop
    with cacheLoopLock:
        if cacheLoop is not None and cacheLoop.is_running():
            return cacheLoop
        loop = asyncio.new_event_loop()
        started = threading.Event()

        def runCacheLoop() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(target=runCacheLoop, name="cashews-cache-loop", daemon=True)
        thread.start()
        loop.call_soon_threadsafe(started.set)
        started.wait(timeout=5.0)
        cacheLoop = loop
        return loop


def runOnCacheLoop(awaitable: Any) -> Any:
    loop = getCacheLoop()
    running: asyncio.AbstractEventLoop | None
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        running = None
    if running is loop:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(awaitable)).result()
    return asyncio.run_coroutine_threadsafe(awaitable, loop).result()


def syncCacheGet(cacheKey: str) -> Any:
    async def getCall() -> Any:
        return await cache.get(cacheKey, default=MISS)

    return runOnCacheLoop(getCall())


def syncCacheSet(cacheKey: str, value: Any, ttl: str) -> None:
    async def setCall() -> None:
        await cache.set(cacheKey, value, expire=ttl)

    runOnCacheLoop(setCall())


def findResponse(args: tuple, kwargs: dict) -> Any:
    for candidate in (*args, *kwargs.values()):
        if hasattr(candidate, "headers") and hasattr(candidate, "status_code"):
            return candidate
    return None


def sync_cache(ttl: str, key: str, headers: dict[str, str] | None = None) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cacheKey = get_cache_key(func, key, args, kwargs)
            response = findResponse(args, kwargs)

            def applyHeaders(value: Any) -> Any:
                if response is not None and headers:
                    for name, headerValue in headers.items():
                        response.headers[name] = headerValue
                return value

            def fetchAndStore() -> Any:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = runOnCacheLoop(result)
                syncCacheSet(cacheKey, result, ttl)
                return result

            cached = syncCacheGet(cacheKey)
            if cached is not MISS:
                return applyHeaders(cached)
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
                return applyHeaders(joined if joined is not MISS else fetchAndStore())
            filled = syncCacheGet(cacheKey)
            if filled is not MISS:
                with flightLock:
                    flights.pop(cacheKey, None)
                flight.set()
                return applyHeaders(filled)
            try:
                return applyHeaders(fetchAndStore())
            finally:
                with flightLock:
                    flights.pop(cacheKey, None)
                flight.set()

        return wrapper  # type: ignore[return-value]

    return decorator


def clearEndpointCache() -> None:
    async def clearPrefixes() -> None:
        await cache.delete_match("stocks:*")
        await cache.delete_match("wallet:*")

    runOnCacheLoop(clearPrefixes())
