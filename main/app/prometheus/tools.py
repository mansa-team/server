import logging

from google.genai import types

from config import SessionLocal
from main.app.prometheus.memory import PrometheusMemory
from main.utils.models.loader import embed

logger = logging.getLogger(__name__)

MEMORY_TOOL_NAMES = {"search_memory", "save_memory"}

MEMORY_TOOLS = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="search_memory",
                description="Search user's saved memories, preferences, and past analysis context.",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "query": types.Schema(type=types.Type.STRING, description="Search query"),
                        "limit": types.Schema(type=types.Type.INTEGER, description="Max results (default 10)"),
                    },
                    required=["query"],
                ),
            ),
            types.FunctionDeclaration(
                name="save_memory",
                description="Store a memory about the user's preferences, analysis results, or feedback. Checks memory limit (5 for free users, 50 for premium).",
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties={
                        "key": types.Schema(type=types.Type.STRING, description="Short label for the memory"),
                        "value": types.Schema(type=types.Type.STRING, description="Full memory content"),
                        "type": types.Schema(
                            type=types.Type.STRING,
                            enum=["preference", "analysis", "feedback", "context"],
                            description="Type of memory",
                        ),
                    },
                    required=["key", "value", "type"],
                ),
            ),
        ]
    )
]


async def executeMemoryTool(name: str, args: dict, user: dict) -> dict:
    db = SessionLocal()
    try:
        if name == "search_memory":
            results = PrometheusMemory.search(
                db,
                user["userId"],
                args["query"],
                limit=args.get("limit", 10),
            )
            return {"memories": results}

        elif name == "save_memory":
            embedding = embed([args["value"]])[0]
            result = PrometheusMemory.upsertMemory(
                db,
                user["userId"],
                key=args["key"],
                value=args["value"],
                memoryType=args["type"],
                source="explicit",
                embedding=embedding,
                userRoles=user.get("roles", []),
            )
            if result["status"] == "limit_reached":
                return {"error": f"Memory limit reached ({result['limit']}). Upgrade to premium for 50 memories."}
            return {"status": result["status"], "memoryId": result["memory"].id}

        return {"error": f"Unknown memory tool: {name}"}
    finally:
        db.close()


async def dispatchToolCall(functionCall, mcpClients, user=None) -> dict:
    name = functionCall.name
    args = functionCall.args or {}
    logger.info(f"Executing tool call: {name}({args})")

    if name in MEMORY_TOOL_NAMES and user:
        return await executeMemoryTool(name, args, user)

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
            logger.debug(f"Client {client} failed for {name}: {e}")
            continue

    return {"error": f"Tool '{name}' not available"}
