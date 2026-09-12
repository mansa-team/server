import hashlib
import math
from datetime import datetime

import numpy as np

from main.utils.models.loader import getEmbeddingModel


def normalizeRows(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.where(norms == 0, 1.0, norms)


def embed(texts: list[str]) -> list[list[float]]:
    return getEmbeddingModel().encode(texts, normalize_embeddings=True).tolist()


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
    qNorm = float(np.linalg.norm(q))
    if qNorm == 0:
        return np.zeros(matrix.shape[0], dtype=np.float32)
    return normalizeRows(matrix) @ (q / qNorm)


def contentHash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8"), usedforsecurity=False).hexdigest()


def getRelevanceScore(memory, now: datetime) -> float:
    if memory.lastAccessedAt is None:
        lastAccessed = memory.createdAt.replace(tzinfo=None) if memory.createdAt.tzinfo else memory.createdAt
    else:
        lastAccessed = memory.lastAccessedAt
        if lastAccessed.tzinfo is not None:
            lastAccessed = lastAccessed.replace(tzinfo=None)
    nowNaive = now.replace(tzinfo=None) if now.tzinfo is not None else now
    days = max((nowNaive - lastAccessed).total_seconds() / 86400, 0)
    stability = max(getattr(memory, "score", 7.0), 0.1)

    return math.exp(-days / stability)
