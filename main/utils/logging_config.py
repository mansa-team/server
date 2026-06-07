import logging
import threading
from typing import Optional
import requests

from config import Config
from slowapi import Limiter
from slowapi.util import get_remote_address
from main.utils.errors import RequestContextFilter

limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)


def setupLogging():
    root = logging.getLogger()
    level = logging.DEBUG if Config.DEBUG_MODE else logging.ERROR
    root.setLevel(level)

    request_filter = RequestContextFilter()

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    console.addFilter(request_filter)
    root.addHandler(console)


class DiscordHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        if not Config.DISCORD.ENABLED or not Config.DISCORD.WEBHOOK_URL:
            return

        if record.levelno < logging.ERROR:
            return

        module = record.name.split(".")[-1]
        message = record.getMessage()

        payload = {"content": f"[{record.levelname}] [{module}] {message}"}

        try:
            threading.Thread(
                target=lambda: requests.post(Config.DISCORD.WEBHOOK_URL, json=payload, timeout=5), daemon=True
            ).start()
        except Exception as e:
            logger.debug(f"Discord webhook failed: {e}")


def setupDiscordHandler():
    if Config.DISCORD.ENABLED and Config.DISCORD.WEBHOOK_URL:
        logging.getLogger().addHandler(DiscordHandler())


setupLogging()
setupDiscordHandler()
