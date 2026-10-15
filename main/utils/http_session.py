import threading

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

local = threading.local()


def getSession() -> requests.Session:
    if not hasattr(local, "session"):
        session = requests.Session()
        retries = Retry(
            total=2,
            backoff_factor=0.5,
            status_forcelist=(500, 502, 503, 504),
            allowed_methods={"GET"},
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        local.session = session
    return local.session


def isTransientError(exc: BaseException) -> bool:
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    if isinstance(exc, requests.exceptions.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", None)
        return isinstance(status, int) and status >= 500
    return False
