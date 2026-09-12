import threading
from typing import Any, Callable

import numpy as np

matrixStore: dict[Any, tuple[list[int], np.ndarray]] = {}
matrixLock = threading.Lock()


def getMatrix(userId: Any, loader: Callable[[], tuple[list[int], np.ndarray]]) -> tuple[list[int], np.ndarray]:
    with matrixLock:
        if userId in matrixStore:
            return matrixStore[userId]
    freshIds, freshMatrix = loader()
    with matrixLock:
        if userId in matrixStore:
            return matrixStore[userId]
        matrixStore[userId] = (freshIds, freshMatrix)
        return matrixStore[userId]


def invalidateUser(userId: int) -> None:
    with matrixLock:
        for cacheKey in [k for k in matrixStore if k == userId or (isinstance(k, tuple) and k and k[0] == userId)]:
            matrixStore.pop(cacheKey, None)


def clearAll() -> None:
    with matrixLock:
        matrixStore.clear()
