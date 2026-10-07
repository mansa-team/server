import asyncio
import logging
from collections.abc import MutableMapping
from config import Config, SessionLocal
import json
import unicodedata
from datetime import datetime, timezone
from typing import Any, Callable, cast

from cashews import Cache
from google import genai
from google.genai import types
import numpy as np
from pydantic import BaseModel, TypeAdapter
from rapidfuzz import fuzz

from sqlalchemy import func, desc
from sqlalchemy.dialects.mysql import match as mysqlMatch
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, defer

from main.models.memory import OrunmilaMemory as OrunmilaMemoryModel
from main.utils.roles import Permission, Roles

from main.app.orunmila.vector import batchCosineSimilarity, contentHash, decodeEmbeddings, getRelevanceScore, embed
from main.app.orunmila.chat import OrunmilaChatManager
from main.app.orunmila.compact import countTokens

matrixCache = Cache()
matrixCache.setup("mem://")

MATRIX_MISS = object()


def getMatrix(userId: Any, loader: Callable[[], tuple[list[int], np.ndarray]]) -> tuple[list[int], np.ndarray]:
    if isinstance(userId, tuple):
        uid, memoryType = userId
        cacheKey = f"matrix:{uid}:{memoryType}:v{1}"
    else:
        uid = userId
        cacheKey = f"matrix:{userId}:v{1}"
    cached = asyncio.run(matrixCache.get(cacheKey, default=MATRIX_MISS))
    if cached is not MATRIX_MISS:
        return cast(tuple[list[int], np.ndarray], cached)
    freshIds, freshMatrix = loader()
    asyncio.run(matrixCache.set(cacheKey, (freshIds, freshMatrix), tags=("matrix", f"matrix-user:{uid}")))
    return cast(
        tuple[list[int], np.ndarray],
        asyncio.run(matrixCache.get(cacheKey, default=(freshIds, freshMatrix))),
    )


def invalidateUser(userId: int) -> None:
    asyncio.run(matrixCache.delete_tags(f"matrix-user:{userId}"))


def clearAll() -> None:
    asyncio.run(matrixCache.clear())


logger = logging.getLogger(__name__)


class MemoryCandidate(BaseModel):
    key: str
    value: str
    type: str = "context"


candidateAdapter = TypeAdapter(MemoryCandidate)

MEMORY_LIMIT_BASIC = 50
MEMORY_LIMIT_EXTENDED = 250

INITIAL_STABILITY = {
    "preference": 14.0,  # sticky - forgets slowly
    "analysis": 7.0,  # medium - forgets normally
    "feedback": 10.0,  # medium - sticky
    "context": 3.0,  # ephemeral - forgets fast
}

MEMORY_EXTRACTION_TOKEN_BUDGET = 32000
MEMORY_EXTRACT_FREE_CAP = 5
MEMORY_EXTRACT_PREMIUM_CAP = 10

TOKEN_CACHE_MAXSIZE = 2048
TOKEN_CACHE_TTL_SECONDS = 3600


client = None


def getClient():
    global client
    if client is None:
        client = genai.Client(api_key=Config.ORUNMILA.GEMINI_API_KEY)
    return client


def minMax(values: list[float]) -> list[float]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        return [0.0 for _ in values]
    return [(v - lo) / (hi - lo) for v in values]


def normalizeKey(key: str) -> str:
    normalized = key.lower().replace("_", " ")
    normalized = "".join(c for c in unicodedata.normalize("NFKD", normalized) if not unicodedata.combining(c))

    return " ".join(normalized.split())


def findSimilarKey(db: Session, userId: int, newKey: str, threshold: float = 0.8) -> OrunmilaMemoryModel | None:
    existing = (
        db.query(OrunmilaMemoryModel)
        .filter(OrunmilaMemoryModel.userId == userId, OrunmilaMemoryModel.archivedAt.is_(None))
        .all()
    )
    newNormalized = normalizeKey(newKey)

    for m in existing:
        existingNormalized = normalizeKey(str(m.memoryKey))

        if not newNormalized and not existingNormalized:
            continue

        if fuzz.ratio(newNormalized, existingNormalized) > threshold * 100:
            return m

    return None


def scoreRecency(candidateRows: list[Any], limit: int) -> list[dict]:
    now = datetime.now()
    scored = []
    for m in candidateRows:
        s = getRelevanceScore(m, now)
        scored.append(
            {
                "id": m.id,
                "memoryKey": m.memoryKey,
                "memoryValue": m.memoryValue,
                "memoryType": m.memoryType,
                "score": s,
                "relevanceScore": s,
                "similarity": 0.0,
            }
        )
    scored.sort(key=lambda x: float(x["score"]), reverse=True)  # type: ignore[arg-type]
    return scored[:limit]


def scoreCandidates(
    candidateRows: list[Any],
    vecNorm: list[float],
    simById: dict[int, float],
    ftRank: dict[int, float],
    now: datetime,
    limit: int,
) -> list[dict]:
    fused: list[tuple[Any, float, float]] = []
    for m, v in zip(candidateRows, vecNorm):
        rec = getRelevanceScore(m, now)
        f = 0.6 * v + 0.25 * ftRank.get(cast(int, m.id), 0.0) + 0.15 * rec
        fused.append((m, f, simById.get(cast(int, m.id), 0.0)))
    fused.sort(key=lambda p: p[1], reverse=True)
    return [
        {
            "id": m.id,
            "memoryKey": m.memoryKey,
            "memoryValue": m.memoryValue,
            "memoryType": m.memoryType,
            "score": f,
            "relevanceScore": f,
            "similarity": sim,
        }
        for m, f, sim in fused[:limit]
    ]


class OrunmilaMemory:
    @classmethod
    def getMemoryLimit(cls, userRoles: list[str]) -> int:
        if Roles.checkAccess(userRoles, Permission.ORUNMILA_EXTENDED_MEMORIES):
            return MEMORY_LIMIT_EXTENDED
        return MEMORY_LIMIT_BASIC

    @staticmethod
    def touch(m: Any, value: str, memoryType: str, source: str, embedding: Any, newHash: str) -> None:
        m.memoryValue = value  # type: ignore[assignment]
        m.memoryType = memoryType  # type: ignore[assignment]
        m.source = source  # type: ignore[assignment]
        m.contentHash = newHash  # type: ignore[assignment]
        m.embedding = embedding  # type: ignore[assignment]
        m.score = m.score * 1.1  # type: ignore[assignment]
        m.accessCount += 1  # type: ignore[assignment]
        m.lastAccessedAt = datetime.now()  # type: ignore[assignment]

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
            db.query(OrunmilaMemoryModel)
            .filter(OrunmilaMemoryModel.userId == userId, OrunmilaMemoryModel.memoryKey == key)
            .first()
        )

        if existing:
            newHash = contentHash(value)
            if existing.contentHash == newHash:
                return {"status": "unchanged", "memory": existing}

            cls.touch(existing, value, memoryType, source, embedding, newHash)

            db.commit()
            db.refresh(existing)
            invalidateUser(userId)

            return {"status": "updated", "memory": existing}

        similar = findSimilarKey(db, userId, key)
        if similar:
            cls.touch(similar, value, memoryType, source, embedding, contentHash(value))

            db.commit()
            db.refresh(similar)
            invalidateUser(userId)

            return {"status": "merged", "memory": similar}

        if userRoles:
            limit = cls.getMemoryLimit(userRoles)
            current = cls.countMemories(db, userId)
            if current >= limit:
                return {"status": "limit_reached", "limit": limit, "current": current}

        memory = OrunmilaMemoryModel(
            userId=userId,
            memoryKey=key,
            memoryValue=value,
            memoryType=memoryType,
            source=source,
            embedding=embedding,
            contentHash=contentHash(value),
            score=INITIAL_STABILITY.get(str(memoryType)),
            lastAccessedAt=datetime.now(),
        )
        db.add(memory)
        db.commit()
        db.refresh(memory)
        invalidateUser(userId)
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
            db.query(OrunmilaMemoryModel)
            .filter(OrunmilaMemoryModel.userId == userId)
            .filter(OrunmilaMemoryModel.archivedAt.is_(None))
        )

        if memoryType:
            queryFilter = queryFilter.filter(OrunmilaMemoryModel.memoryType == memoryType)

        candidateRows = (
            queryFilter.options(defer(cast(Any, OrunmilaMemoryModel.embedding)))
            .order_by(OrunmilaMemoryModel.score.desc())
            .limit(500)
            .all()
        )
        if not candidateRows:
            return []
        candidateIds = [r.id for r in candidateRows]

        if not query or len(query.strip()) < 3:
            return scoreRecency(candidateRows, limit)

        try:
            simById: dict[int, float] = {}

            def loadMatrix() -> tuple[list[int], np.ndarray]:
                embRows = db.query(OrunmilaMemoryModel).filter(OrunmilaMemoryModel.id.in_(candidateIds)).all()
                rowsWithEmb = [m for m in embRows if m.embedding is not None]
                if not rowsWithEmb:
                    return ([], np.empty((0, 0), dtype=np.float32))
                rawEmbs = [m.embedding for m in rowsWithEmb]
                if isinstance(rawEmbs[0], (bytes, bytearray, memoryview)):
                    return ([cast(int, m.id) for m in rowsWithEmb], decodeEmbeddings(rawEmbs))  # type: ignore[arg-type]
                return ([cast(int, m.id) for m in rowsWithEmb], np.array(rawEmbs, dtype=np.float32))

            try:
                cachedIds, matrix = getMatrix((userId, memoryType), loadMatrix)
                if cachedIds and matrix.shape[0] > 0:
                    queryEmbedding = embed([query])[0]
                    sims = batchCosineSimilarity(queryEmbedding, matrix)
                    simById = {mid: float(s) for mid, s in zip(cachedIds, sims)}
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                logger.warning(f"Embedding scoring failed, using full-text and recency only: {e}")
            vecScores = [simById.get(cast(int, m.id), 0.0) for m in candidateRows]
            vecNorm = minMax(vecScores)
            ftRows = cls.fullTextSearch(db, userId, query, 500)
            ftRank = {r["id"]: 1.0 / (i + 1) for i, r in enumerate(ftRows)}
            now = datetime.now(timezone.utc)
            return scoreCandidates(candidateRows, vecNorm, simById, ftRank, now, limit)
        except (SQLAlchemyError, ValueError, TypeError, AttributeError) as e:
            logger.warning(f"Fused search failed, falling back to full-text: {e}")

        return cls.fullTextSearch(db, userId, query, limit)

    @classmethod
    def fullTextSearch(cls, db: Session, userId: int, query: str, limit: int) -> list[dict]:
        if db.bind is not None and db.bind.dialect.name == "mysql":
            matchExpr = mysqlMatch(
                OrunmilaMemoryModel.memoryKey,
                OrunmilaMemoryModel.memoryValue,
                against=query,
                in_boolean_mode=True,
            )
            results = (
                db.query(
                    OrunmilaMemoryModel.id,
                    OrunmilaMemoryModel.memoryKey,
                    OrunmilaMemoryModel.memoryValue,
                    OrunmilaMemoryModel.memoryType,
                    OrunmilaMemoryModel.score,
                    matchExpr.label("matchScore"),
                )
                .filter(OrunmilaMemoryModel.userId == userId)
                .filter(OrunmilaMemoryModel.archivedAt.is_(None))
                .order_by(desc("matchScore"), desc(OrunmilaMemoryModel.score))
                .limit(limit)
                .all()
            )
            return [
                {
                    "id": r.id,
                    "memoryKey": r.memoryKey,
                    "memoryValue": r.memoryValue,
                    "memoryType": r.memoryType,
                    "score": float(r.matchScore),
                    "relevanceScore": float(r.score),
                }
                for r in results
            ]

        like = f"%{query}%"
        results = (
            db.query(OrunmilaMemoryModel)
            .filter(OrunmilaMemoryModel.userId == userId)
            .filter(OrunmilaMemoryModel.archivedAt.is_(None))
            .filter(OrunmilaMemoryModel.memoryKey.like(like) | OrunmilaMemoryModel.memoryValue.like(like))
            .order_by(OrunmilaMemoryModel.score.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": m.id,
                "memoryKey": m.memoryKey,
                "memoryValue": m.memoryValue,
                "memoryType": m.memoryType,
                "score": float(m.score),
                "relevanceScore": float(m.score),
            }
            for m in results
        ]

    @classmethod
    def countMemories(cls, db: Session, userId: int) -> int:
        return (
            db.query(func.count(OrunmilaMemoryModel.id))
            .filter(OrunmilaMemoryModel.userId == userId)
            .filter(OrunmilaMemoryModel.archivedAt.is_(None))
            .scalar()
            or 0
        )

    @classmethod
    def getUserMemories(cls, db: Session, userId: int, limit: int = 50, offset: int = 0) -> list[dict]:
        memories = (
            db.query(OrunmilaMemoryModel)
            .filter(OrunmilaMemoryModel.userId == userId)
            .filter(OrunmilaMemoryModel.archivedAt.is_(None))
            .order_by(OrunmilaMemoryModel.score.desc())
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
                "relevanceScore": getRelevanceScore(m, datetime.now()),
                "accessCount": m.accessCount,
                "createdAt": m.createdAt.isoformat() if m.createdAt else None,
            }
            for m in memories
        ]

    @classmethod
    def deleteMemory(cls, db: Session, userId: int, memoryId: int) -> bool:
        memory = (
            db.query(OrunmilaMemoryModel)
            .filter(OrunmilaMemoryModel.id == memoryId, OrunmilaMemoryModel.userId == userId)
            .first()
        )

        if not memory:
            return False

        memory.archivedAt = datetime.now()  # type: ignore[assignment]

        db.commit()
        invalidateUser(userId)

        return True

    @staticmethod
    def extract(
        db: Session | None = None, userId=None, sessionId=None, userRoles=None, tokenCache: MutableMapping | None = None
    ) -> list[OrunmilaMemoryModel]:
        ownSession = db is None
        if ownSession:
            db = SessionLocal()
        try:
            if db is None:
                logger.error("Failed to acquire DB session for memory search")
                return []
            cap = (
                MEMORY_EXTRACT_PREMIUM_CAP
                if Roles.checkAccess(userRoles, Permission.ORUNMILA_EXTENDED_MEMORIES)
                else MEMORY_EXTRACT_FREE_CAP
            )

            watermark = (
                db.query(func.max(OrunmilaMemoryModel.createdAt)).filter(OrunmilaMemoryModel.userId == userId).scalar()
            )
            msgs = OrunmilaChatManager.getHistory(db, sessionId, limit=200, since=watermark)

            acc = []
            tokens = 0
            for msg in reversed(msgs):
                text = (msg.get("parts") or [{}])[0].get("text", "")
                acc.append(text)
                if tokenCache is None:
                    tokens += countTokens(text)
                else:
                    cached = tokenCache.get(text)
                    if cached is None:
                        cached = countTokens(text)
                        tokenCache[text] = cached
                    tokens += cached
                if tokens >= MEMORY_EXTRACTION_TOKEN_BUDGET:
                    break

            if tokens < MEMORY_EXTRACTION_TOKEN_BUDGET:
                return []

            remaining = OrunmilaMemory.getMemoryLimit(userRoles) - OrunmilaMemory.countMemories(db, userId)
            if remaining <= 0:
                return []
            n = min(cap, remaining)

            transcript = "\n".join(reversed(acc))
            try:
                response = getClient().models.generate_content(
                    model="gemini-flash-lite-latest",
                    contents=[EXTRACT_PROMPT + "\n\n" + transcript],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        temperature=0.2,
                        response_schema=types.Schema(
                            type=types.Type.ARRAY,
                            items=types.Schema(
                                type=types.Type.OBJECT,
                                properties={
                                    "key": types.Schema(type=types.Type.STRING),
                                    "value": types.Schema(type=types.Type.STRING),
                                    "type": types.Schema(
                                        type=types.Type.STRING,
                                        enum=["preference", "analysis", "feedback", "context"],
                                    ),
                                },
                                required=["key", "value", "type"],
                            ),
                        ),
                    ),
                )
                rawCandidates = json.loads(response.text)
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                logger.warning("Memory extraction LLM call failed: %s", e)
                return []

            if not isinstance(rawCandidates, list):
                return []

            candidates: list[MemoryCandidate] = []
            for raw in rawCandidates:
                try:
                    candidates.append(candidateAdapter.validate_python(raw))
                except (ValueError, TypeError) as e:
                    logger.warning("Memory extraction dropped invalid item: %s", e)
            if not candidates:
                return []

            created = []
            cands = candidates[:n]
            try:
                embeddings = embed([c.value for c in cands])
            except (OSError, RuntimeError, ValueError, TypeError) as e:
                logger.warning("Memory batch embedding failed: %s", e)
                embeddings = []
            for idx, cand in enumerate(cands):
                try:
                    if idx < len(embeddings):
                        embedding = embeddings[idx]
                    else:
                        embedding = embed([cand.value])[0]
                    result = OrunmilaMemory.upsertMemory(
                        db,
                        userId,
                        key=cand.key,
                        value=cand.value,
                        memoryType=cand.type,
                        source="inferred",
                        embedding=embedding,
                        userRoles=userRoles,
                    )
                    created.append(result["memory"])
                except SQLAlchemyError as e:
                    logger.warning("Memory upsert failed: %s", e)
            return created
        finally:
            if ownSession and db is not None:
                db.close()


EXTRACT_PROMPT = (
    "Extraia memorias duradouras desta conversa para uso em sessoes futuras. "
    "Inclua: preferencias do usuario, conclusoes de analises, tickers/temas recorrentes, feedback. "
    "Retorne SOMENTE JSON no formato: "
    '[{"key": "rotulo curto", "value": "detalhe", "type": "preference|analysis|feedback|context"}]. '
    "Apenas fatos presentes no texto. Maximo 10 itens. Ignore conversa efemera."
)
