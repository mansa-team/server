import logging
import logging.handlers
import threading
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

        exc_text = ""
        if record.exc_info and record.exc_info[1]:
            exc_text = logging.Formatter().formatException(record.exc_info)

        full_text = f"[{record.levelname}] [{module}] {message}"
        if exc_text:
            full_text += f"\n{exc_text}"

        MAX_MESSAGE_LENGTH = 2000
        if len(full_text) > MAX_MESSAGE_LENGTH:
            full_text = full_text[: MAX_MESSAGE_LENGTH - 20] + "\n...[truncated]"

        payload = {"content": full_text}

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
