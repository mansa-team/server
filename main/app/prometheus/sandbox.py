import json
import logging
import os

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


def _getClient() -> AsyncClient:
    return AsyncClient(base_url=FORGEVM_URL, timeout=30)


class SandboxManager:
    @staticmethod
    async def create(userId: int) -> str:
        client = _getClient()
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
        """Return existing sandbox if alive, otherwise create a new one.

        When a DB session is provided, sandbox↔user mappings are persisted
        so that subsequent calls can reconnect instead of spawning fresh.
        """
        if db:
            mapping = db.query(PrometheusSandbox).filter_by(userId=userId).first()
            if mapping:
                client = _getClient()
                try:
                    sandbox_id_str: str = str(mapping.sandboxId)
                    sandbox = await client.get(sandbox_id_str)
                    await sandbox.extend_ttl(SANDBOX_TTL_RENEW)
                    logger.info("Reused sandbox %s for user %d", sandbox_id_str, userId)
                    return sandbox_id_str
                except Exception:
                    # Sandbox is dead — clean up stale mapping, fall through to create
                    logger.info("Sandbox %s dead for user %d, respawning", mapping.sandboxId, userId)
                    db.delete(mapping)
                    db.commit()

        # Create fresh sandbox
        sandbox_id = await SandboxManager.create(userId)

        # Restore from backup if one exists on host
        backup = await SandboxManager._loadBackup(userId)
        if backup:
            await SandboxManager.restoreWorkspace(sandbox_id, backup)

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
    async def execute(sandboxId: str, code: str, timeout: int = 30) -> dict:
        client = _getClient()
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
    async def read_file(sandboxId: str, path: str) -> str:
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            return await sandbox.read_file(path)
        finally:
            await client.close()

    @staticmethod
    async def write_file(sandboxId: str, path: str, content: str) -> bool:
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            await sandbox.write_file(path, content)
            return True
        except Exception:
            return False
        finally:
            await client.close()

    @staticmethod
    async def list_files(sandboxId: str, path: str = "/workspace") -> dict:
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            entries = await sandbox.list_files(path)
            return {"entries": entries}
        finally:
            await client.close()

    @staticmethod
    async def syncWorkspace(sandboxId: str) -> dict:
        """Snapshot every file in /workspace as a {path: content} dict."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            paths: list[str] = await sandbox.glob_files("/workspace/**")
            files: dict[str, str] = {}
            for p in paths:
                files[p] = await sandbox.read_file(p)
            return files
        finally:
            await client.close()

    @staticmethod
    async def restoreWorkspace(sandboxId: str, files: dict) -> None:
        """Write a {path: content} dict back into the sandbox."""
        client = _getClient()
        try:
            sandbox = await client.get(sandboxId)
            for path, content in files.items():
                await sandbox.write_file(path, content)
        finally:
            await client.close()

    @staticmethod
    async def _saveBackup(userId: int, files: dict) -> None:
        """Persist workspace files to the host volume as JSON."""
        backup_dir = os.path.join(WORKSPACE_ROOT, str(userId))
        os.makedirs(backup_dir, exist_ok=True)
        backup_file = os.path.join(backup_dir, "backup.json")
        with open(backup_file, "w") as f:
            json.dump(files, f)

    @staticmethod
    async def _loadBackup(userId: int) -> dict:
        """Load workspace backup from host volume, or return {} if none."""
        backup_file = os.path.join(WORKSPACE_ROOT, str(userId), "backup.json")
        if not os.path.exists(backup_file):
            return {}
        with open(backup_file) as f:
            return json.load(f)

    @staticmethod
    async def destroy(sandboxId: str, userId: int | None = None, db: Session | None = None) -> None:
        """Destroy a sandbox and optionally remove its DB mapping."""
        client = _getClient()
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
