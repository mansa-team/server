from datetime import datetime, timedelta

import numpy as np
from pytz import timezone
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from main.models.memory import UserMemory
from main.utils.roles import Permission, Roles
from main.app.prometheus.vector import batchCosineSimilarity, contentHash, getRelevanceScore

MEMORY_LIMIT_BASIC = 5
MEMORY_LIMIT_EXTENDED = 50


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

        now = datetime.now(timezone("America/Sao_Paulo"))
        memoriesWithEmb = [m for m in memories if m.embedding is not None]
        if memoriesWithEmb:
            try:
                from main.utils.models.loader import embed as _embed

                queryEmbedding = _embed([query])[0]
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
                            "relevanceScore": getRelevanceScore(m, now),
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
        now = datetime.now(timezone("America/Sao_Paulo"))
        return [
            {
                "id": m.id,
                "memoryKey": m.memoryKey,
                "memoryValue": m.memoryValue,
                "memoryType": m.memoryType,
                "relevanceScore": getRelevanceScore(m, now),
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

    @classmethod
    def archiveDead(cls, db: Session):
        threshold = datetime.now(timezone("America/Sao_Paulo")) - timedelta(days=180)
        dead = (
            db.query(UserMemory)
            .filter(UserMemory.baseScore < 0.1)
            .filter((UserMemory.lastAccessedAt < threshold) | UserMemory.lastAccessedAt.is_(None))
            .all()
        )
        for m in dead:
            m.archivedAt = datetime.now(timezone("America/Sao_Paulo"))  # type: ignore[assignment]
        db.commit()
