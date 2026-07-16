import pytest
import numpy as np
from main.models.types import VectorType


class TestVectorType:
    def test_roundtrip(self):
        """VectorType: list → bytes → list preserves data."""
        vt = VectorType(384)
        original = [0.1] * 384
        bound = vt.process_bind_param(original, None)
        result = vt.process_result_value(bound, None)
        assert isinstance(result, list)
        assert len(result) == 384
        np.testing.assert_allclose(result, original, atol=1e-6)

    def test_none_roundtrip(self):
        """VectorType: None passes through."""
        vt = VectorType(384)
        assert vt.process_bind_param(None, None) is None
        assert vt.process_result_value(None, None) is None

    def test_wrong_dims_raises(self):
        """VectorType: rejects wrong dimension."""
        vt = VectorType(384)
        with pytest.raises(ValueError, match="384-dim"):
            vt.process_bind_param([0.1] * 100, None)

    def test_preserves_negative_values(self):
        """VectorType: handles negative floats."""
        vt = VectorType(384)
        original = [float(i - 192) for i in range(384)]
        bound = vt.process_bind_param(original, None)
        result = vt.process_result_value(bound, None)
        np.testing.assert_allclose(result, original, atol=1e-6)

    def test_large_random_vector(self):
        """VectorType: random 384-dim vector roundtrips."""
        vt = VectorType(384)
        rng = np.random.default_rng(42)
        original = rng.standard_normal(384).astype(np.float32).tolist()
        bound = vt.process_bind_param(original, None)
        result = vt.process_result_value(bound, None)
        np.testing.assert_allclose(result, original, atol=1e-6)
