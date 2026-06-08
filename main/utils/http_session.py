import threading
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
