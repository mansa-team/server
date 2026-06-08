import threading
import atexit
import logging
import requests

logger = logging.getLogger(__name__)


local = threading.local()


def getSession() -> requests.Session:
    if not hasattr(local, "session"):
        local.session = requests.Session()
    return local.session


def cleanup():
    if hasattr(local, "session"):
        try:
            local.session.close()
        except Exception:
            logger.debug("Failed to close session during cleanup", exc_info=True)


atexit.register(cleanup)
