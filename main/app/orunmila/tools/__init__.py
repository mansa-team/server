import logging
import asyncio
from typing import Any, Optional

from main.app.orunmila.tools.memory import save_memory, search_memory
from main.app.orunmila.tools.sandbox import execute_code, list_files, read_file, serve_file, write_file

logger = logging.getLogger(__name__)


# Local in-process tools only. Wallet tools are served exclusively by the
# wallet MCP server (/wallet/mcp): their names are absent here on purpose, so
# dispatchToolCall routes them to the wallet MCP client with the session JWT
# injected as an argument.
TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "execute_code": execute_code,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "serve_file": serve_file,
}


async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    db=None,
    sandbox_id: Optional[str] = None,
    rawToken: Optional[str] = None,
) -> dict:
    name = functionCall.name
    args = dict(functionCall.args or {})
    logger.info(f"Executing tool call: {name}({args})")

    if name in TOOL_REGISTRY:
        fn = TOOL_REGISTRY[name]
        args["user"] = user
        args["db"] = db
        args["sandbox_id"] = sandbox_id
        args["userId"] = user.get("userId", 0) if user else 0
        return await fn(**args)

    for serverName, client in mcpClients.items():
        try:
            callArgs = dict(args)
            if rawToken and serverName == "wallet":
                callArgs["authorization"] = f"Bearer {rawToken}"
            mcpResult = await client.session.call_tool(name, callArgs)
            if getattr(mcpResult, "isError", False):
                continue
            textParts = []
            if hasattr(mcpResult, "content") and mcpResult.content:
                for block in mcpResult.content:
                    textParts.append(block.text if hasattr(block, "text") else str(block))
            return {"result": "\n".join(textParts) if textParts else str(mcpResult)}
        except (OSError, asyncio.TimeoutError, TimeoutError, ConnectionError, ValueError, RuntimeError) as e:
            logger.debug(f"MCP client failed for {name}: {e}")
            continue

    return {"error": f"Tool '{name}' not available"}
