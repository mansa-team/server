import logging
from urllib.parse import quote

from forgevm.exceptions import SandboxNotFound

from main.app.orunmila.sandbox import SandboxManager, hostPath

logger = logging.getLogger(__name__)


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
