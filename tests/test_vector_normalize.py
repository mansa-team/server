import numpy as np
from main.app.prometheus.vector import normalizeRows, batchCosineSimilarity


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
