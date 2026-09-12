import numpy as np
import pytest
from main.app.prometheus.vector import decodeEmbeddings, normalizeRows, batchCosineSimilarity


def test_normalizeRows_unitNormAndZeroGuard():
    m = normalizeRows(np.array([[3.0, 4.0], [0.0, 0.0]], dtype=np.float32))
    assert abs(float(np.linalg.norm(m[0])) - 1.0) < 1e-5
    assert float(np.linalg.norm(m[1])) == 0.0


def test_dotEqualsCosineOnUnnormalized():
    rng = np.random.default_rng(7)
    mat = rng.normal(size=(8, 16)).astype(np.float32) * 5.0
    q = (rng.normal(size=(16,)) * 5.0).tolist()
    got = batchCosineSimilarity(q, mat)
    qn = np.array(q, dtype=np.float32)
    qn /= np.linalg.norm(qn)
    mn = mat / np.linalg.norm(mat, axis=1, keepdims=True)
    np.testing.assert_allclose(got, mn @ qn, rtol=1e-4, atol=1e-5)


def test_decodeEmbeddings_listMatchesBytes():
    rng = np.random.default_rng(11)
    mat = rng.normal(size=(4, 8)).astype(np.float32)
    byteRows = [r.tobytes() for r in mat]
    listRows = [r.tolist() for r in mat]
    fromBytes = decodeEmbeddings(byteRows)
    fromLists = decodeEmbeddings(listRows)
    np.testing.assert_allclose(fromLists, fromBytes, rtol=1e-6, atol=1e-7)
    np.testing.assert_allclose(fromLists, mat, rtol=1e-6, atol=1e-7)


def test_decodeEmbeddings_mixedDimsRaise():
    with pytest.raises(ValueError):
        decodeEmbeddings([[1.0, 2.0, 3.0], [1.0, 2.0]])


def test_decodeEmbeddings_emptyReturnsZeroRows():
    got = decodeEmbeddings([])
    assert got.shape == (0, 0)
    assert got.dtype == np.float32
