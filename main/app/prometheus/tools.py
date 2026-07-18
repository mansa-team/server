import logging
from config import SessionLocal
from typing import Any

from forgevm.exceptions import SandboxNotFound

from main.app.prometheus.memory import PrometheusMemory
from main.app.prometheus.sandbox import SandboxManager
from main.app.prometheus.vector import embed

logger = logging.getLogger(__name__)


#
# memory
#
async def search_memory(query: str, limit: int = 10, **_) -> dict:
    """Search user's saved memories, preferences, and past analysis context.

    Use this to recall what the user has previously discussed, their preferences, or past analysis results before starting a new analysis.

    Args:
        query: Search query — keywords or phrase to find in saved memories
        limit: Maximum number of memories to return (default 10)
    """
    user = _.get("user")
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


async def save_memory(key: str, value: str, type: str, **_) -> dict:
    """Store a memory about the user's preferences, analysis results, or feedback.

    Use this to remember important findings, user preferences, or analysis conclusions across sessions.

    Args:
        key: Short label for the memory (e.g., "PETR4 valuation")
        value: Full memory content with details
        type: Type of memory — one of: preference, analysis, feedback, context
    """
    user = _.get("user")
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
async def get_state(key: str = "", **_) -> dict:
    """Retrieve values from the harness state. Use this to recall intermediate results,
    analysis progress, or user preferences stored during this session.

    Args:
        key: Optional key to retrieve. If empty, returns all state.
    """
    state = _.get("state")
    if not state:
        return {"error": "State not available"}
    if key:
        return {key: state.get(key)}
    return state.to_dict()


async def set_state(key: str, value: str, **_) -> dict:
    """Store a value in the harness state for this session. Use this to save
    intermediate analysis results, track progress, or remember user preferences.

    Args:
        key: State key (e.g., "current_step", "petr4_pe_ratio")
        value: Value to store (will be converted to string)
    """
    state = _.get("state")
    if not state:
        return {"error": "State not available"}
    state.set(key, value)
    return {"status": "ok", "key": key}


#
# sandbox
#
async def execute_code(code: str, timeout: int = 30, **_) -> dict:
    """Execute Python code in an isolated sandbox. Use for quantitative analysis,
    statistical models, custom charts, and data transformations.

    Args:
        code: Python code to execute
        timeout: Maximum execution time in seconds (default 30)
    """
    userId = _.get("userId", 0)
    sandboxId = _.get("sandbox_id")
    if not sandboxId:
        return {"error": "No sandbox available"}
    try:
        return await SandboxManager.execute(userId, code, sandboxId, timeout=timeout)
    except SandboxNotFound:
        return {"error": "Sandbox could not be respawned. Try again."}
    except Exception as e:
        logger.error("Sandbox execution failed: %s", e)
        return {"error": f"Sandbox execution failed: {e}"}


async def read_file(path: str, **_) -> dict:
    """Read a file from the workspace.

    Args:
        path: Path to the file (e.g., /workspace/results.json or results.json)
    """
    userId = _.get("userId", 0)
    content = SandboxManager.read_file(userId, path)
    return {"content": content}


async def write_file(path: str, content: str, **_) -> dict:
    """Write a file to the workspace. Use this to save data files
    (CSV, JSON, scripts) for analysis.

    Args:
        path: Path where the file will be written (e.g., /workspace/analyze.py)
        content: File content as a string
    """
    userId = _.get("userId", 0)
    ok = SandboxManager.write_file(userId, path, content)
    return {"success": ok}


async def list_files(path: str = "/workspace", **_) -> dict:
    """List files in the workspace directory.

    Args:
        path: Directory path to list (default: /workspace)
    """
    userId = _.get("userId", 0)
    return SandboxManager.list_files(userId, path)


TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "get_state": get_state,
    "set_state": set_state,
    "execute_code": execute_code,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
}


async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    state=None,
    sandbox_id: str | None = None,
) -> dict:
    name = functionCall.name
    args = dict(functionCall.args or {})
    logger.info(f"Executing tool call: {name}({args})")

    if name in TOOL_REGISTRY:
        fn = TOOL_REGISTRY[name]
        args["user"] = user
        args["state"] = state
        args["sandbox_id"] = sandbox_id
        args["userId"] = user.get("userId", 0) if user else 0
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
