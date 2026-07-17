import logging
from typing import Any

from config import SessionLocal
from main.app.prometheus.memory import PrometheusMemory
from main.app.prometheus.sandbox import SandboxManager
from main.app.prometheus.state import HarnessState
from main.app.prometheus.vector import embed

logger = logging.getLogger(__name__)


#
# memory
#
async def search_memory(query: str, limit: int = 10, user: dict | None = None, **_) -> dict:
    """Search user's saved memories, preferences, and past analysis context.

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
    """Store a memory about the user's preferences, analysis results, or feedback.

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


#
# harness state
#
async def get_state(key: str = "", state: HarnessState | None = None, **_) -> dict:
    """Retrieve values from the harness state. Use this to recall intermediate results,
    analysis progress, or user preferences stored during this session.

    Args:
        key: Optional key to retrieve. If empty, returns all state.
    """
    if not state:
        return {"error": "State not available"}
    if key:
        return {key: state.get(key)}
    return state.to_dict()


async def set_state(key: str, value: str, state: HarnessState | None = None, **_) -> dict:
    """Store a value in the harness state for this session. Use this to save
    intermediate analysis results, track progress, or remember user preferences.

    Args:
        key: State key (e.g., "current_step", "petr4_pe_ratio")
        value: Value to store (will be converted to string)
    """
    if not state:
        return {"error": "State not available"}
    state.set(key, value)
    return {"status": "ok", "key": key}


#
# sandbox tools
#
async def execute_code(code: str, timeout: int = 30, *, sandbox_id: str | None = None, cache=None, **kwargs) -> dict:
    """Execute Python code in an isolated sandbox. Use for quantitative analysis,
    statistical models, custom charts, and data transformations.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 30)
    """
    if not sandbox_id:
        return {"error": "Sandbox not available. This feature requires a premium subscription."}

    # Check cache first
    if cache:
        code_hash = cache.compute_hash(code)
        cached = cache.get(code_hash)
        if cached:
            cached["cached"] = True
            return cached

    result = await SandboxManager.execute(sandbox_id, code, timeout)

    # Cache the result
    output = {
        "stdout": result.get("stdout", ""),
        "stderr": result.get("stderr", ""),
    }
    if cache:
        code_hash = cache.compute_hash(code)
        cache.set(code_hash, output)

    return output


async def read_sandbox_file(path: str, *, sandbox_id: str | None = None, **kwargs) -> dict:
    """Read a file from the sandbox filesystem.

    Args:
        path: Absolute path to the file in the sandbox
    """
    if not sandbox_id:
        return {"error": "Sandbox not available"}
    content = await SandboxManager.read_file(sandbox_id, path)
    return {"content": content}


async def check_cache(code_hash: str, *, cache=None, **kwargs) -> dict:
    """Check if a computed result exists in the cache. Use before executing
    expensive code to avoid redundant computation.

    Args:
        code_hash: SHA256 hash of the code to check
    """
    if not cache:
        return {"error": "Cache not available"}
    cached = cache.get(code_hash)
    if cached:
        return {"hit": True, "result": cached}
    return {"hit": False}


TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "get_state": get_state,
    "set_state": set_state,
    "execute_code": execute_code,
    "read_sandbox_file": read_sandbox_file,
    "check_cache": check_cache,
}


async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    state=None,
    sandbox_id: str | None = None,
    cache=None,
) -> dict:
    name = functionCall.name
    args = dict(functionCall.args or {})
    logger.info(f"Executing tool call: {name}({args})")

    if name in TOOL_REGISTRY:
        fn = TOOL_REGISTRY[name]
        args["user"] = user
        args["state"] = state
        args["sandbox_id"] = sandbox_id
        args["cache"] = cache
        return await fn(**args)

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
