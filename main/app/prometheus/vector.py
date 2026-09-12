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

    firstIsBytes = isinstance(rawEmbeddings[0], (bytes, bytearray, memoryview))
    if firstIsBytes:
        byteRows = [bytes(r) if isinstance(r, (bytearray, memoryview)) else r for r in rawEmbeddings]
        if any(not isinstance(r, bytes) for r in byteRows):
            raise ValueError("Mixed embedding row types: expected all bytes-like or all float sequences")
        dims = len(byteRows[0]) // 4  # float32 = 4 bytes
        if any(len(r) // 4 != dims or len(r) % 4 != 0 for r in byteRows):
            raise ValueError("Inconsistent embedding dims across rows")
        buf = b"".join(byteRows)
        return np.frombuffer(buf, dtype=np.float32).reshape(len(byteRows), dims)

    rows = [np.array(r, dtype=np.float32).reshape(-1) for r in rawEmbeddings]
    dims = int(rows[0].shape[0])
    if any(int(r.shape[0]) != dims for r in rows):
        raise ValueError("Inconsistent embedding dims across rows")
    return np.stack(rows).astype(np.float32)


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
