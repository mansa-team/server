import numpy as np
from main.app.prometheus.matrix_cache import getMatrix, invalidateUser, clearAll


def test_cache_hitAndInvalidate():
    clearAll()
    calls = {"n": 0}

    def loader():
        calls["n"] += 1
        return ([1, 2], np.eye(2, dtype=np.float32))

    ids1, m1 = getMatrix(3, loader)
    ids2, m2 = getMatrix(3, loader)
    assert calls["n"] == 1 and ids1 == ids2
    invalidateUser(3)
    getMatrix(3, loader)
    assert calls["n"] == 2
