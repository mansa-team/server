import threading

import requests


local = threading.local()


def getSession() -> requests.Session:
    if not hasattr(local, "session"):
        local.session = requests.Session()
    return local.session


def isTransientError(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return isinstance(status, int) and status >= 500
    return False
