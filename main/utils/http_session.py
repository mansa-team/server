import threading
import atexit
import requests


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
            pass


atexit.register(cleanup)
