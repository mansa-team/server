import asyncio
import threading
from typing import Any, Callable

import numpy as np
from cashews import cache

try:
    from cashews.defaults import _empty as MISS
except ImportError:  # pragma: no cover - private import fallback
    MISS = object()

MATRIX_CACHE_VERSION = 1

cache.setup("mem://")

trackedKeys: set[str] = set()
trackedLock = threading.Lock()


def buildKey(userId: Any) -> str:
    if isinstance(userId, tuple):
        uid, memoryType = userId
        return f"matrix:{uid}:{memoryType}:v{MATRIX_CACHE_VERSION}"
    return f"matrix:{userId}:v{MATRIX_CACHE_VERSION}"


def runAwait(coro: Any) -> Any:
    return asyncio.run(coro)


def getMatrix(userId: Any, loader: Callable[[], tuple[list[int], np.ndarray]]) -> tuple[list[int], np.ndarray]:
    cacheKey = buildKey(userId)
    cached = runAwait(cache.get(cacheKey, default=MISS))
    if cached is not MISS:
        return cached  # type: ignore[no-any-return]
    freshIds, freshMatrix = loader()
    runAwait(cache.set(cacheKey, (freshIds, freshMatrix)))
    with trackedLock:
        trackedKeys.add(cacheKey)
    return runAwait(cache.get(cacheKey, default=(freshIds, freshMatrix)))


def invalidateUser(userId: int) -> None:
    prefix = f"matrix:{userId}:"
    with trackedLock:
        doomed = [k for k in trackedKeys if k == f"matrix:{userId}:v{MATRIX_CACHE_VERSION}" or k.startswith(prefix)]
        for cacheKey in doomed:
            trackedKeys.discard(cacheKey)
    for cacheKey in doomed:
        runAwait(cache.delete(cacheKey))


def clearAll() -> None:
    with trackedLock:
        doomed = [k for k in trackedKeys if k.startswith("matrix:")]
        trackedKeys.clear()
    for cacheKey in doomed:
        runAwait(cache.delete(cacheKey))
