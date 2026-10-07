import logging
import asyncio
from typing import Any, Optional

from main.app.orunmila.tools.memory import save_memory, search_memory
from main.app.orunmila.tools.sandbox import execute_code, list_files, read_file, serve_file, write_file
from main.app.orunmila.tools.wallet import (
    wallet_allocation,
    wallet_performance,
    wallet_positions,
    wallet_rebalance,
    wallet_summary,
    list_wallet_earnings,
)

logger = logging.getLogger(__name__)


TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "execute_code": execute_code,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "serve_file": serve_file,
    "wallet_positions": wallet_positions,
    "wallet_summary": wallet_summary,
    "wallet_allocation": wallet_allocation,
    "list_wallet_earnings": list_wallet_earnings,
    "wallet_performance": wallet_performance,
    "wallet_rebalance": wallet_rebalance,
}


async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    db=None,
    sandbox_id: Optional[str] = None,
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
        except (OSError, asyncio.TimeoutError, TimeoutError, ConnectionError, ValueError, RuntimeError) as e:
            logger.debug(f"MCP client failed for {name}: {e}")
            continue

    return {"error": f"Tool '{name}' not available"}
