import numpy as np
import pytest
from main.app.prometheus.vector import batchCosineSimilarity, contentHash


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
