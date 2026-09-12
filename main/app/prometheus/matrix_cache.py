import numpy as np

_store: dict[int, tuple[list[int], np.ndarray]] = {}


def getMatrix(userId: int, loader) -> tuple[list[int], np.ndarray]:
    if userId not in _store:
        _store[userId] = loader()
    return _store[userId]


def invalidateUser(userId: int) -> None:
    _store.pop(userId, None)


def clearAll() -> None:
    _store.clear()
