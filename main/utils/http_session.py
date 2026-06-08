import threading
import atexit
import requests


_local = threading.local()


def get_session() -> requests.Session:
    """Return a requests.Session for the current thread.

    Sessions are created lazily and stored in a threading.local()
    so each thread gets its own isolated Session instance.  This avoids
    the documented non-thread-safety of ``requests.Session`` when used
    across a ``ThreadPoolExecutor``.
    """
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
    return _local.session


def _cleanup():
    """Close the main thread's session at interpreter shutdown."""
    if hasattr(_local, "session"):
        try:
            _local.session.close()
        except Exception:
            pass


atexit.register(_cleanup)
