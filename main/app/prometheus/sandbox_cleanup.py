import logging

from main.app.prometheus.sandbox import _getClient
from main.models.sandbox import PrometheusSandbox

logger = logging.getLogger(__name__)


async def cleanup_expired_sandboxes(db=None):
    """Remove DB mappings for sandboxes that no longer exist in ForgeVM."""
    if db is None:
        from config import SessionLocal

        db = SessionLocal()
        close_db = True
    else:
        close_db = False

    try:
        mappings = db.query(PrometheusSandbox).all()
        cleaned = 0
        for mapping in mappings:
            client = _getClient()
            try:
                await client.get(mapping.sandboxId)
            except Exception:
                db.delete(mapping)
                cleaned += 1
                logger.info(
                    "Cleaned dead sandbox mapping: user=%d sandbox=%s",
                    mapping.userId,
                    mapping.sandboxId,
                )
            finally:
                await client.close()
        db.commit()
        return cleaned
    finally:
        if close_db:
            db.close()
