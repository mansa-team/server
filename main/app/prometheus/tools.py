import logging
from typing import Any

from config import SessionLocal
from main.app.prometheus.memory import PrometheusMemory
from main.app.prometheus.state import HarnessState
from main.app.prometheus.vector import embed

logger = logging.getLogger(__name__)


async def search_memory(query: str, limit: int = 10, user: dict | None = None, **_) -> dict:
    """
    Search user's saved memories, preferences, and past analysis context.

    Use this to recall what the user has previously discussed, their preferences, or past analysis results before starting a new analysis.

    Args:
        query: Search query — keywords or phrase to find in saved memories
        limit: Maximum number of memories to return (default 10)
    """
    if not user:
        return {"error": "Authentication required"}

    db = SessionLocal()
    try:
        results = PrometheusMemory.search(
            db,
            user["userId"],
            query,
            limit=limit,
        )
        return {"memories": results}
    finally:
        db.close()


async def save_memory(key: str, value: str, type: str, user: dict | None = None, **_) -> dict:
    """
    Store a memory about the user's preferences, analysis results, or feedback.

    Use this to remember important findings, user preferences, or analysis conclusions across sessions.

    Args:
        key: Short label for the memory (e.g., "PETR4 valuation")
        value: Full memory content with details
        type: Type of memory — one of: preference, analysis, feedback, context
    """
    if not user:
        return {"error": "Authentication required"}

    db = SessionLocal()
    try:
        embedding = embed([value])[0]
        result = PrometheusMemory.upsertMemory(
            db,
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
        db.close()


TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
}

STATE_TOOL_NAMES = {"get_state", "set_state"}


def get_state(key: str = "") -> str:
    """Retrieve values from the harness state. Use this to recall intermediate results,
    analysis progress, or user preferences stored during this session.

    Args:
        key: Optional key to retrieve. If empty, returns all state.
    """
    pass


def set_state(key: str, value: str) -> str:
    """Store a value in the harness state for this session. Use this to save
    intermediate analysis results, track progress, or remember user preferences.

    Args:
        key: State key (e.g., "current_step", "petr4_pe_ratio")
        value: Value to store (will be converted to string)
    """
    pass


STATE_TOOLS = [get_state, set_state]


async def executeStateTool(name: str, args: dict, state: HarnessState) -> dict:
    if name == "get_state":
        key = args.get("key", "")
        if key:
            return {key: state.get(key)}
        return state.to_dict()

    if name == "set_state":
        state.set(args["key"], args["value"])
        return {"status": "ok", "key": args["key"]}

    return {"error": f"Unknown state tool: {name}"}


async def dispatchToolCall(functionCall, mcpClients, user=None, state=None) -> dict:
    name = functionCall.name
    args = dict(functionCall.args or {})
    logger.info(f"Executing tool call: {name}({args})")

    if name in TOOL_REGISTRY:
        fn = TOOL_REGISTRY[name]
        args["user"] = user
        return await fn(**args)

    if name in STATE_TOOL_NAMES and state:
        return await executeStateTool(name, args, state)

    for client in mcpClients.values():
        try:
            mcpResult = await client.session.call_tool(name, args)
            if getattr(mcpResult, "isError", False):
                continue
            textParts = []
            if hasattr(mcpResult, "content") and mcpResult.content:
                for block in mcpResult.content:
                    textParts.append(block.text if hasattr(block, "text") else str(block))
            return {"result": "\n".join(textParts) if textParts else str(mcpResult)}
        except Exception as e:
            logger.debug(f"MCP client failed for {name}: {e}")
            continue

    return {"error": f"Tool '{name}' not available"}
