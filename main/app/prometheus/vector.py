import hashlib
import math
from datetime import datetime

import numpy as np

from main.utils.models.loader import getEmbeddingModel


def embed(texts: list[str]) -> list[list[float]]:
    return getEmbeddingModel().encode(texts).tolist()


def decodeEmbeddings(rawEmbeddings: list[bytes]) -> np.ndarray:
    if not rawEmbeddings:
        return np.empty((0, 0), dtype=np.float32)

    buf = b"".join(rawEmbeddings)
    dims = len(rawEmbeddings[0]) // 4  # float32 = 4 bytes
    return np.frombuffer(buf, dtype=np.float32).reshape(len(rawEmbeddings), dims)


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
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def getRelevanceScore(memory, now: datetime) -> float:
    if memory.lastAccessedAt is None:
        return memory.baseScore
    lastAccessed = memory.lastAccessedAt

    if lastAccessed.tzinfo is not None:
        lastAccessed = lastAccessed.replace(tzinfo=None)
    nowNaive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    days = max((nowNaive - lastAccessed).total_seconds() / 86400, 0)
    timeFactor = 1.0 / (1.0 + math.log1p(days) * 0.7)
    return memory.baseScore * timeFactor
