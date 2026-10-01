import asyncio

from main.app.orunmila.memory import OrunmilaMemory
from main.app.orunmila.vector import embed
from main.app.orunmila.tools.context import closeOwnSession, popAuthSession


async def search_memory(query: str, limit: int = 10, **_) -> dict:
    """Search user's saved memories, preferences, and past analysis context.

    Use this to recall what the user has previously discussed, their preferences, or past analysis results before starting a new analysis.

    Args:
        query: Search query — keywords or phrase to find in saved memories
        limit: Maximum number of memories to return (default 10)
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        results = await asyncio.to_thread(
            OrunmilaMemory.search,
            db,  # type: ignore[arg-type]
            user["userId"],
            query,
            limit=limit,
        )
        return {"memories": results}
    finally:
        closeOwnSession(db, ownSession)


async def save_memory(key: str, value: str, type: str, **_) -> dict:
    """Store a memory about the user's preferences, analysis results, or feedback.

    Use this to remember important findings, user preferences, or analysis conclusions across sessions.

    Args:
        key: Short label for the memory (e.g., "PETR4 valuation")
        value: Full memory content with details
        type: Type of memory — one of: preference, analysis, feedback, context
    """
    user, db, ownSession, authError = popAuthSession(_)
    if authError is not None:
        return authError
    try:
        embedding = embed([value])[0]
        result = await asyncio.to_thread(
            OrunmilaMemory.upsertMemory,
            db,  # type: ignore[arg-type]
            user["userId"],
            key=key,
            value=value,
            memoryType=type,
            source="explicit",
            embedding=embedding,
            userRoles=user.get("roles", []),
        )
        if result["status"] == "limit_reached":
            return {"error": f"Memory limit reached ({result['limit']}). Upgrade to premium for more memories."}
        return {"status": result["status"], "memoryId": result["memory"].id}
    finally:
        closeOwnSession(db, ownSession)
