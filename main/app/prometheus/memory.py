import logging
import unicodedata
from datetime import datetime

import numpy as np
from pytz import timezone
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from main.models.memory import PrometheusMemory as PrometheusMemoryModel
from main.utils.roles import Permission, Roles
from main.app.prometheus.vector import batchCosineSimilarity, contentHash, getRelevanceScore, embed

logger = logging.getLogger(__name__)

MEMORY_LIMIT_BASIC = 50
MEMORY_LIMIT_EXTENDED = 250


def normalizeKey(key: str) -> set[str]:
    normalized = key.lower().replace("_", " ")
    normalized = "".join(c for c in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(c))

    return set(normalized.split())


def findSimilarKey(db: Session, userId: int, newKey: str, threshold: float = 0.8) -> PrometheusMemoryModel | None:
    existing = (
        db.query(PrometheusMemoryModel)
        .filter(PrometheusMemoryModel.userId == userId, PrometheusMemoryModel.archivedAt.is_(None))
        .all()
    )
    newTokens = normalizeKey(newKey)

    for m in existing:
        existingTokens = normalizeKey(str(m.memoryKey))
        union = newTokens | existingTokens

        if not union:
            continue

        similarity = len(newTokens & existingTokens) / len(union)

        if similarity > threshold:
            return m

    return None


def _applyUpdate(memory, value, memoryType, source, embedding):
    memory.memoryValue = value  # type: ignore[assignment]
    memory.memoryType = memoryType  # type: ignore[assignment]
    memory.source = source  # type: ignore[assignment]
    memory.contentHash = contentHash(value)  # type: ignore[assignment]
    memory.embedding = embedding  # type: ignore[assignment]
    memory.baseScore = min(memory.baseScore + 0.1, 1.0)  # type: ignore[arg-type]
    memory.accessCount += 1  # type: ignore[assignment]
    memory.lastAccessedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]


class PrometheusMemory:
    @classmethod
    def getMemoryLimit(cls, userRoles: list[str]) -> int:
        if Roles.checkAccess(userRoles, Permission.PROMETHEUS_EXTENDED_MEMORIES):
            return MEMORY_LIMIT_EXTENDED
        return MEMORY_LIMIT_BASIC

    @classmethod
    def countMemories(cls, db: Session, userId: int) -> int:
        return (
            db.query(func.count(PrometheusMemoryModel.id))
            .filter(PrometheusMemoryModel.userId == userId)
            .filter(PrometheusMemoryModel.archivedAt.is_(None))
            .scalar()
        )

    @classmethod
    def upsertMemory(
        cls,
        db: Session,
        userId: int,
        key: str,
        value: str,
        memoryType: str = "context",
        source: str = "inferred",
        embedding=None,
        userRoles: list[str] | None = None,
    ) -> dict:
        existing = (
            db.query(PrometheusMemoryModel)
            .filter(PrometheusMemoryModel.userId == userId, PrometheusMemoryModel.memoryKey == key)
            .first()
        )

        if existing:
            newHash = contentHash(value)
            if existing.contentHash == newHash:
                return {"status": "unchanged", "memory": existing}

            _applyUpdate(existing, value, memoryType, source, embedding)

            db.commit()
            db.refresh(existing)

            return {"status": "updated", "memory": existing}

        similar = findSimilarKey(db, userId, key)
        if similar:
            _applyUpdate(similar, value, memoryType, source, embedding)

            db.commit()
            db.refresh(similar)

            return {"status": "merged", "memory": similar}

        if userRoles:
            limit = cls.getMemoryLimit(userRoles)
            current = cls.countMemories(db, userId)
            if current >= limit:
                return {"status": "limit_reached", "limit": limit, "current": current}

        memory = PrometheusMemoryModel(
            userId=userId,
            memoryKey=key,
            memoryValue=value,
            memoryType=memoryType,
            source=source,
            embedding=embedding,
            contentHash=contentHash(value),
            lastAccessedAt=datetime.now(timezone("America/Sao_Paulo")),
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        return {"status": "created", "memory": memory}

    @classmethod
    def search(
        cls,
        db: Session,
        userId: int,
        query: str,
        limit: int = 10,
        memoryType: str | None = None,
    ) -> list[dict]:
        queryFilter = (
            db.query(PrometheusMemoryModel)
            .filter(PrometheusMemoryModel.userId == userId)
            .filter(PrometheusMemoryModel.archivedAt.is_(None))
        )

        if memoryType:
            queryFilter = queryFilter.filter(PrometheusMemoryModel.memoryType == memoryType)

        memories = queryFilter.all()
        if not memories:
            return []

        memoriesWithEmb = [m for m in memories if m.embedding is not None]
        if memoriesWithEmb:
            try:
                queryEmbedding = embed([query])[0]
                matrix = np.vstack([m.embedding for m in memoriesWithEmb])
                similarities = batchCosineSimilarity(queryEmbedding, matrix)

                results = []
                for i, m in enumerate(memoriesWithEmb):
                    results.append(
                        {
                            "id": m.id,
                            "memoryKey": m.memoryKey,
                            "memoryValue": m.memoryValue,
                            "memoryType": m.memoryType,
                            "score": float(similarities[i]),
                            "relevanceScore": getRelevanceScore(m, datetime.now(timezone("America/Sao_Paulo"))),
                        }
                    )
                results.sort(key=lambda x: float(x["score"]), reverse=True)  # type: ignore[arg-type]

                return results[:limit]
            except Exception as e:
                logger.warning(f"Embedding search failed, falling back to full-text: {e}")

        return cls.fullTextSearch(db, userId, query, limit)

    @classmethod
    def fullTextSearch(cls, db: Session, userId: int, query: str, limit: int) -> list[dict]:
        results = (
            db.execute(
                text("""
                SELECT id, memoryKey, memoryValue, memoryType, baseScore,
                       MATCH(memoryKey, memoryValue) AGAINST(:query IN BOOLEAN MODE) as score
                FROM prometheus_memories
                WHERE userId = :userId
                  AND archivedAt IS NULL
                ORDER BY score DESC, baseScore DESC
                LIMIT :limit
            """),
                {"query": query, "userId": userId, "limit": limit},
            )
            .mappings()
            .all()
        )

        return [
            {
                "id": r["id"],
                "memoryKey": r["memoryKey"],
                "memoryValue": r["memoryValue"],
                "memoryType": r["memoryType"],
                "score": float(r["score"]),
                "relevanceScore": float(r["baseScore"]),
            }
            for r in results
        ]

    @classmethod
    def getUserMemories(cls, db: Session, userId: int, limit: int = 50, offset: int = 0) -> list[dict]:
        memories = (
            db.query(PrometheusMemoryModel)
            .filter(PrometheusMemoryModel.userId == userId)
            .filter(PrometheusMemoryModel.archivedAt.is_(None))
            .order_by(PrometheusMemoryModel.baseScore.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )

        return [
            {
                "id": m.id,
                "memoryKey": m.memoryKey,
                "memoryValue": m.memoryValue,
                "memoryType": m.memoryType,
                "relevanceScore": getRelevanceScore(m, datetime.now(timezone("America/Sao_Paulo"))),
                "accessCount": m.accessCount,
                "createdAt": m.createdAt.isoformat() if m.createdAt else None,
            }
            for m in memories
        ]

    @classmethod
    def deleteMemory(cls, db: Session, userId: int, memoryId: int) -> bool:
        memory = (
            db.query(PrometheusMemoryModel)
            .filter(PrometheusMemoryModel.id == memoryId, PrometheusMemoryModel.userId == userId)
            .first()
        )

        if not memory:
            return False

        memory.archivedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]

        db.commit()

        return True
