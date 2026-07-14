import hashlib
import numpy as np


def batchCosineSimilarity(query: list[float], matrix: np.ndarray) -> np.ndarray:
    if matrix.shape[0] == 0:
        return np.array([], dtype=np.float32)
    q = np.array(query, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1)
    q_norm = np.linalg.norm(q)
    if q_norm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)
    norms = np.where(norms == 0, 1e-8, norms)
    return (matrix @ q) / (norms * q_norm)


def contentHash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()
