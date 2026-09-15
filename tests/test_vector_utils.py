import numpy as np
import pytest
from main.app.prometheus.vector import (
    batchCosineSimilarity,
    contentHash,
    decodeEmbeddings,
    normalizeRows,
    toVectorString,
    fromVectorString,
)


class TestBatchCosineSimilarity:
    def test_empty_matrix(self):
        result = batchCosineSimilarity([1.0, 0.0], np.array([]).reshape(0, 2))
        assert len(result) == 0

    def test_single_row(self):
        q = [1.0, 0.0]
        matrix = np.array([[1.0, 0.0]], dtype=np.float32)
        result = batchCosineSimilarity(q, matrix)
        assert result[0] == pytest.approx(1.0)

    def test_multiple_rows(self):
        q = [1.0, 0.0]
        matrix = np.array(
            [
                [0.0, 1.0],
                [1.0, 0.0],
                [-1.0, 0.0],
            ],
            dtype=np.float32,
        )
        result = batchCosineSimilarity(q, matrix)
        assert result[0] == pytest.approx(0.0)
        assert result[1] == pytest.approx(1.0)
        assert result[2] == pytest.approx(-1.0)

    def test_zero_query(self):
        matrix = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
        result = batchCosineSimilarity([0.0, 0.0], matrix)
        np.testing.assert_array_equal(result, [0.0, 0.0])


class TestContentHash:
    def test_deterministic(self):
        assert contentHash("hello") == contentHash("hello")

    def test_different_inputs(self):
        assert contentHash("hello") != contentHash("world")

    def test_hex_format(self):
        h = contentHash("test")
        assert len(h) == 32
        assert all(c in "0123456789abcdef" for c in h)


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


def test_codec_roundTrip():
    vec = [0.5, -0.25, 0.125]
    assert fromVectorString(toVectorString(vec), dims=3) == vec


def test_codec_rejectsBadDims():
    with pytest.raises(ValueError):
        fromVectorString("[0.1,0.2]", dims=3)
