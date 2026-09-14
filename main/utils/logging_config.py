import atexit
import logging
import time
from collections import deque
from logging.handlers import QueueHandler, QueueListener
from queue import Queue

import requests

from config import Config
from main.utils.errors import RequestContextFilter
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)

discordQueue: Queue = Queue()


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
    def __init__(self):
        super().__init__()
        self.recent: deque[str] = deque(maxlen=100)

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
        self.acquire()
        try:
            if text in self.recent:
                return
            self.recent.append(text)
        finally:
            self.release()
        try:
            requests.post(Config.DISCORD.WEBHOOK_URL, json={"content": text}, timeout=10)
        except Exception:
            pass  # nosec: B110 per-message send failure swallowed, retried on next error
        time.sleep(0.45)  # ~5 msgs/2s, under discord rate limit


def setupDiscordHandler():
    if not (Config.DISCORD.ENABLED and Config.DISCORD.WEBHOOK_URL):
        return

    listener = QueueListener(discordQueue, DiscordHandler())
    listener.start()
    atexit.register(listener.stop)
    logging.getLogger().addHandler(QueueHandler(discordQueue))


setupLogging()
setupDiscordHandler()
