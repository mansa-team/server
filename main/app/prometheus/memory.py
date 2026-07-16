import unicodedata
from datetime import datetime

import numpy as np
from pytz import timezone
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from main.models.memory import UserMemory
from main.utils.roles import Permission, Roles
from main.app.prometheus.vector import batchCosineSimilarity, contentHash, getRelevanceScore, embed

MEMORY_LIMIT_BASIC = 5
MEMORY_LIMIT_EXTENDED = 50


def _normalize_key(key: str) -> set[str]:
    normalized = key.lower().replace("_", " ")
    normalized = "".join(c for c in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(c))
    return set(normalized.split())


def _findSimilarKey(db: Session, userId: int, newKey: str, threshold: float = 0.8) -> UserMemory | None:
    existing = (
        db.query(UserMemory)
        .filter(UserMemory.userId == userId, UserMemory.archivedAt.is_(None))
        .all()
    )
    newTokens = _normalize_key(newKey)
    for m in existing:
        existingTokens = _normalize_key(m.memoryKey)
        union = newTokens | existingTokens
        if not union:
            continue
        similarity = len(newTokens & existingTokens) / len(union)
        if similarity > threshold:
            return m
    return None


class PrometheusMemory:
    @classmethod
    def getMemoryLimit(cls, userRoles: list[str]) -> int:
        if Roles.checkAccess(userRoles, Permission.PROMETHEUS_EXTENDED_MEMORIES):
            return MEMORY_LIMIT_EXTENDED
        return MEMORY_LIMIT_BASIC

    @classmethod
    def countMemories(cls, db: Session, userId: int) -> int:
        return (
            db.query(func.count(UserMemory.id))
            .filter(UserMemory.userId == userId)
            .filter(UserMemory.archivedAt.is_(None))
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
        existing = db.query(UserMemory).filter(UserMemory.userId == userId, UserMemory.memoryKey == key).first()

        if existing:
            newHash = contentHash(value)
            if existing.contentHash == newHash:
                return {"status": "unchanged", "memory": existing}

            existing.memoryValue = value  # type: ignore[assignment]
            existing.memoryType = memoryType  # type: ignore[assignment]
            existing.source = source  # type: ignore[assignment]
            existing.contentHash = newHash  # type: ignore[assignment]
            existing.embedding = embedding  # type: ignore[assignment]
            existing.baseScore = min(existing.baseScore + 0.1, 1.0)  # type: ignore[arg-type]
            existing.accessCount += 1  # type: ignore[assignment]
            existing.lastAccessedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]
            db.commit()
            db.refresh(existing)
            return {"status": "updated", "memory": existing}

        similar = _findSimilarKey(db, userId, key)
        if similar:
            similar.memoryValue = value  # type: ignore[assignment]
            similar.memoryType = memoryType  # type: ignore[assignment]
            similar.source = source  # type: ignore[assignment]
            similar.contentHash = contentHash(value)  # type: ignore[assignment]
            similar.embedding = embedding  # type: ignore[assignment]
            similar.baseScore = min(similar.baseScore + 0.1, 1.0)  # type: ignore[arg-type]
            similar.accessCount += 1  # type: ignore[assignment]
            similar.lastAccessedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]
            db.commit()
            db.refresh(similar)
            return {"status": "merged", "memory": similar}

        if userRoles:
            limit = cls.getMemoryLimit(userRoles)
            current = cls.countMemories(db, userId)
            if current >= limit:
                return {"status": "limit_reached", "limit": limit, "current": current}

        memory = UserMemory(
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
        queryFilter = db.query(UserMemory).filter(UserMemory.userId == userId).filter(UserMemory.archivedAt.is_(None))
        if memoryType:
            queryFilter = queryFilter.filter(UserMemory.memoryType == memoryType)

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
            except Exception:
                pass

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

        now = datetime.now(timezone("America/Sao_Paulo"))
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
            db.query(UserMemory)
            .filter(UserMemory.userId == userId)
            .filter(UserMemory.archivedAt.is_(None))
            .order_by(UserMemory.baseScore.desc())
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
        memory = db.query(UserMemory).filter(UserMemory.id == memoryId, UserMemory.userId == userId).first()
        if not memory:
            return False
        memory.archivedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]
        db.commit()
        return True
