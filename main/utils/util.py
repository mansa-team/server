from config import Config

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

def log(tag: str, message: str):
    if Config.DEBUG_MODE == "TRUE":
        print(f"[{tag.upper()}] {message}")