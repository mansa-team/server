import threading
import requests


local = threading.local()


def getSession() -> requests.Session:
    if not hasattr(local, "session"):
        local.session = requests.Session()
    return local.session
