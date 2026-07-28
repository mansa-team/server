import atexit
import logging
import threading
import time
from collections import deque

import requests

from config import Config
from main.utils.errors import RequestContextFilter
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)

queue: deque[str] = deque()
lock = threading.Lock()
event = threading.Event()


def setupLogging():
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if Config.DEBUG_MODE else logging.ERROR)

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    console.addFilter(RequestContextFilter())
    root.addHandler(console)


class DiscordHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        if record.levelno < logging.ERROR:
            return
        module = record.name.split(".")[-1]
        text = f"[{record.levelname}] [{module}] {record.getMessage()}"
        if record.exc_info and record.exc_info[1]:
            text += f"\n{logging.Formatter().formatException(record.exc_info)}"

        if not Config.DISCORD.ENABLED or not Config.DISCORD.WEBHOOK_URL:
            return
        text = text[:1980] + "\n...[truncated]" if len(text) > 2000 else text
        with lock:
            if text not in queue:
                queue.append(text)
        event.set()


def setupDiscordHandler():
    if not (Config.DISCORD.ENABLED and Config.DISCORD.WEBHOOK_URL):
        return

    def sender():
        while True:
            event.wait()
            event.clear()
            while True:
                with lock:
                    if not queue:
                        break
                    msg = queue.popleft()
                try:
                    requests.post(Config.DISCORD.WEBHOOK_URL, json={"content": msg}, timeout=10)
                except Exception:
                    pass
                time.sleep(0.45)  # ~5 msgs/2s, under discord rate limit

    t = threading.Thread(target=sender, daemon=True, name="discord-sender")
    t.start()
    atexit.register(lambda: (event.set(), t.join(timeout=3)))
    logging.getLogger().addHandler(DiscordHandler())


setupLogging()
setupDiscordHandler()
