import logging
import os
from pathlib import Path

from forgevm import AsyncClient, ExecResult
from sqlalchemy.orm import Session

from config import Config
from main.models.sandbox import PrometheusSandbox

logger = logging.getLogger(__name__)

FORGEVM_URL = Config.PROMETHEUS.get("FORGEVM_URL", "http://forgevm:7423")
WORKSPACE_ROOT = Config.PROMETHEUS.get("WORKSPACE_ROOT", "/data/workspaces")
SANDBOX_IMAGE = Config.PROMETHEUS.get("SANDBOX_IMAGE", "python:3.12-slim")
SANDBOX_MEMORY_MB = Config.PROMETHEUS.get("SANDBOX_MEMORY_MB", 2048)
SANDBOX_CPUS = Config.PROMETHEUS.get("SANDBOX_CPUS", 2)
SANDBOX_TTL_MINUTES = Config.PROMETHEUS.get("SANDBOX_TTL_MINUTES", 30)
SANDBOX_TTL_RENEW = Config.PROMETHEUS.get("SANDBOX_TTL_RENEW", "24h")


def getClient() -> AsyncClient:
    return AsyncClient(base_url=FORGEVM_URL, timeout=30)


def hostPath(userId: int, sandboxPath: str) -> Path:
    rel = sandboxPath.lstrip("/")
    if rel == "workspace":
        return Path(WORKSPACE_ROOT) / str(userId)
    if rel.startswith("workspace/"):
        rel = rel[len("workspace/") :]
    return Path(WORKSPACE_ROOT) / str(userId) / rel


def sandboxPath(hostPath: Path, userId: int) -> str:
    rel = hostPath.relative_to(Path(WORKSPACE_ROOT) / str(userId))
    return f"/workspace/{rel}"


class SandboxManager:
    @staticmethod
    async def create(userId: int) -> str:
        client = getClient()
        try:
            sandbox = await client.spawn(
                image=SANDBOX_IMAGE,
                memory_mb=SANDBOX_MEMORY_MB,
                vcpus=SANDBOX_CPUS,
                ttl=f"{SANDBOX_TTL_MINUTES}m",
            )
            sandbox_id = sandbox.id  # type: ignore[attr-defined]
            logger.info("Sandbox created: %s for user %d", sandbox_id, userId)
            return sandbox_id
        finally:
            await client.close()

    @staticmethod
    async def getOrCreate(userId: int, db: Session | None = None) -> str:
        if db:
            mapping = db.query(PrometheusSandbox).filter_by(userId=userId).first()
            if mapping:
                client = getClient()
                try:
                    sandbox_id_str: str = str(mapping.sandboxId)
                    sandbox = await client.get(sandbox_id_str)
                    await sandbox.extend_ttl(SANDBOX_TTL_RENEW)
                    logger.info("Reused sandbox %s for user %d", sandbox_id_str, userId)
                    return sandbox_id_str
                except Exception:
                    logger.info("Sandbox %s dead for user %d, respawning", mapping.sandboxId, userId)
                    db.delete(mapping)
                    db.commit()

        sandbox_id = await SandboxManager.create(userId)

        if db:
            workspace_path = os.path.join(WORKSPACE_ROOT, str(userId))
            new_mapping = PrometheusSandbox(
                userId=userId,
                sandboxId=sandbox_id,
                workspacePath=workspace_path,
            )
            db.add(new_mapping)
            db.commit()

        return sandbox_id

    @staticmethod
    def read_file(userId: int, path: str) -> str:
        host = hostPath(userId, path)
        if not host.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return host.read_text(encoding="utf-8")

    @staticmethod
    def write_file(userId: int, path: str, content: str) -> bool:
        try:
            host = hostPath(userId, path)
            host.parent.mkdir(parents=True, exist_ok=True)
            host.write_text(content, encoding="utf-8")
            return True
        except Exception as e:
            logger.warning("Failed to write %s: %s", path, e)
            return False

    @staticmethod
    def list_files(userId: int, path: str = "/workspace") -> dict:
        host = hostPath(userId, path)
        if not host.exists():
            return {"entries": []}
        entries = []
        for item in sorted(host.rglob("*")):
            if item.is_file():
                entries.append(str(sandboxPath(item, userId)))
        return {"entries": entries}

    @staticmethod
    async def syncToSandbox(sandboxId: str, userId: int) -> int:
        workspace = Path(WORKSPACE_ROOT) / str(userId)
        if not workspace.exists():
            return 0

        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            count = 0
            for item in workspace.rglob("*"):
                if item.is_file():
                    sandbox_p = f"/workspace/{item.relative_to(workspace)}"
                    await sandbox.write_file(sandbox_p, item.read_text(encoding="utf-8"))
                    count += 1
            return count
        finally:
            await client.close()

    @staticmethod
    async def syncFromSandbox(sandboxId: str, userId: int) -> int:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            paths: list[str] = await sandbox.glob_files("/workspace/**")
            count = 0
            for p in paths:
                try:
                    content = await sandbox.read_file(p)
                    host = hostPath(userId, p)
                    host.parent.mkdir(parents=True, exist_ok=True)
                    host.write_text(content, encoding="utf-8")
                    count += 1
                except Exception as e:
                    logger.warning("Failed to sync %s from sandbox: %s", p, e)
            return count
        finally:
            await client.close()

    @staticmethod
    async def execute(sandboxId: str, code: str, timeout: int = 30) -> dict:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            result: ExecResult = await sandbox.exec(
                command="python3",
                args=["-c", code],
                timeout=f"{timeout}s",
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        finally:
            await client.close()

    @staticmethod
    async def destroy(sandboxId: str, userId: int | None = None, db: Session | None = None) -> None:
        client = getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.destroy()
            logger.info("Sandbox destroyed: %s", sandboxId)
        except Exception as e:
            logger.warning("Failed to destroy sandbox %s: %s", sandboxId, e)
        finally:
            await client.close()

        if userId is not None and db:
            mapping = db.query(PrometheusSandbox).filter_by(userId=userId).first()
            if mapping:
                db.delete(mapping)
                db.commit()
