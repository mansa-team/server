from config import SessionLocal
import asyncio
import logging
from datetime import date as dateType
from typing import Any, Optional
from urllib.parse import quote

from fastapi import HTTPException
from forgevm.exceptions import SandboxNotFound
from sqlalchemy.orm import Session

from main.app.orunmila.memory import OrunmilaMemory
from main.app.orunmila.sandbox import SandboxManager, hostPath
from main.app.orunmila.vector import embed

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

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
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
        if ownSession:
            db.close()  # type: ignore[union-attr]


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

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
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
        if ownSession:
            db.close()  # type: ignore[union-attr]


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
    try:
        content = SandboxManager.read_file(userId, path)
    except ValueError:
        return {"error": "Invalid workspace path"}
    return {"content": content}


async def write_file(path: str, content: str, **_) -> dict:
    """Write a file to the workspace. Use this to save data files
    (CSV, JSON, scripts) for analysis.

    Args:
        path: Path where the file will be written (e.g., /workspace/analyze.py)
        content: File content as a string
    """
    userId = _.get("userId", 0)
    try:
        ok = SandboxManager.write_file(userId, path, content)
    except ValueError:
        return {"error": "Invalid workspace path"}
    return {"success": ok}


async def list_files(path: str = "/workspace", **_) -> dict:
    """List files in the workspace directory.

    Args:
        path: Directory path to list (default: /workspace)
    """
    userId = _.get("userId", 0)
    try:
        return SandboxManager.list_files(userId, path)
    except ValueError:
        return {"error": "Invalid workspace path"}


async def serve_file(path: str, **_) -> dict:
    """Get a download link for a workspace file to share with the user.

    Use this when the user should be able to download or view a file you
    created (reports, CSVs, charts). Returns a markdown link the user can
    click; embed the markdown value in your reply.

    Args:
        path: Path to the file (e.g., /workspace/report.csv)
    """
    userId = _.get("userId", 0)
    try:
        host = hostPath(userId, path)
    except ValueError:
        return {"error": "Invalid workspace path"}
    if not host.exists() or not host.is_file():
        return {"error": f"File not found: {path}"}

    url = f"/orunmila/workspace/download?path={quote(path, safe='/')}"
    return {"url": url, "markdown": f"[{host.name}]({url})"}


#
# wallet
#
async def get_wallet_positions(wallet_id: int, **_) -> dict:
    """List wallet holdings with live prices, equity, allocation, and buy signals.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
    """
    from main.app.wallet.positions import PositionsManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        return PositionsManager.getPositions(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


async def get_wallet_summary(wallet_id: int, **_) -> dict:
    """Summarize applied capital, equity, and variation for a wallet.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to summarize (must belong to the caller)
    """
    from main.app.wallet.summary import SummaryManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        return SummaryManager.getSummary(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


async def get_wallet_allocation(wallet_id: int, group_by: str = "ticker", **_) -> dict:
    """Break wallet equity down by ticker or asset type.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        group_by: Grouping key — "ticker" or "assetType" (default "ticker")
    """
    from main.app.wallet.summary import SummaryManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        return SummaryManager.getAllocation(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            group_by,
        )
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


async def list_wallet_earnings(wallet_id: int, status: Optional[str] = "A Receber", **_) -> dict:
    """List accrued earnings (dividends, JSCP) for a wallet.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        status: Filter by status — "A Receber", "Recebido", or None for all (default "A Receber")
    """
    from main.app.wallet.earnings import EarningsManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        rows = EarningsManager.listEarnings(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            status=status,
        )
        return {
            "wallet_id": wallet_id,
            "status": status,
            "earnings": [
                {
                    "earning_id": int(row.earningId),
                    "ticker": str(row.ticker),
                    "kind": str(row.kind),
                    "ex_date": str(row.exDate),
                    "pay_date": str(row.payDate),
                    "gross": float(row.gross),
                    "net": float(row.netIrAdjusted),
                    "status": str(row.status),
                }
                for row in rows
            ],
        }
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


async def get_wallet_performance(
    wallet_id: int, from_date: str, to_date: str, ticker: Optional[str] = None, **_
) -> dict:
    """Compute time-weighted return, volatility, and dividends for a wallet or ticker.

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
        from_date: Window start as YYYY-MM-DD
        to_date: Window end as YYYY-MM-DD
        ticker: Optional single ticker; omit for the whole wallet
    """
    from main.app.wallet.performance import PerformanceManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    try:
        startDate = dateType.fromisoformat(from_date)
        endDate = dateType.fromisoformat(to_date)
    except ValueError:
        return {"error": "invalid date, use YYYY-MM-DD"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        return PerformanceManager.getPerformance(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
            ticker,
            startDate,
            endDate,
        )
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


async def get_wallet_rebalance(wallet_id: int, **_) -> dict:
    """Show weight-share rebalance deltas per ticker (buy/sell/hold).

    Read-only: never mutates wallet state.

    Args:
        wallet_id: Wallet to inspect (must belong to the caller)
    """
    from main.app.wallet.positions import PositionsManager
    from main.app.wallet.wallets import WalletsManager

    user = _.get("user")
    if not user:
        return {"error": "Authentication required"}

    db: Session | None = _.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    try:
        userId = user["userId"]
        try:
            WalletsManager.getWallet(
                db,  # type: ignore[arg-type]
                wallet_id,
                userId,
            )
        except HTTPException:
            return {"error": "not-owner"}
        return PositionsManager.getRebalance(
            db,  # type: ignore[arg-type]
            wallet_id,
            userId,
        )
    finally:
        if ownSession:
            db.close()  # type: ignore[union-attr]


TOOL_REGISTRY: dict[str, Any] = {
    "search_memory": search_memory,
    "save_memory": save_memory,
    "execute_code": execute_code,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "serve_file": serve_file,
    "get_wallet_positions": get_wallet_positions,
    "get_wallet_summary": get_wallet_summary,
    "get_wallet_allocation": get_wallet_allocation,
    "list_wallet_earnings": list_wallet_earnings,
    "get_wallet_performance": get_wallet_performance,
    "get_wallet_rebalance": get_wallet_rebalance,
}


async def dispatchToolCall(
    functionCall,
    mcpClients,
    user=None,
    db=None,
    sandbox_id: str | None = None,
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
        except Exception as e:
            logger.debug(f"MCP client failed for {name}: {e}")
            continue

    return {"error": f"Tool '{name}' not available"}
