import logging
import logging.handlers
import atexit
from concurrent.futures import ThreadPoolExecutor
import requests

from config import Config
from slowapi import Limiter
from slowapi.util import get_remote_address
from main.utils.errors import RequestContextFilter

limiter = Limiter(key_func=get_remote_address)
logger = logging.getLogger(__name__)

discordExecutor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="discord-webhook")
atexit.register(discordExecutor.shutdown, wait=False)


def setupLogging():
    root = logging.getLogger()
    level = logging.DEBUG if Config.DEBUG_MODE else logging.ERROR
    root.setLevel(level)

    requestFilter = RequestContextFilter()

    console = logging.StreamHandler()
    console.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | [%(request_id)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    console.addFilter(requestFilter)
    root.addHandler(console)


class DiscordHandler(logging.Handler):
    def emit(self, record: logging.LogRecord):
        if not Config.DISCORD.ENABLED or not Config.DISCORD.WEBHOOK_URL:
            return

        if record.levelno < logging.ERROR:
            return

        module = record.name.split(".")[-1]
        message = record.getMessage()

        excText = ""
        if record.exc_info and record.exc_info[1]:
            excText = logging.Formatter().formatException(record.exc_info)

        fullText = f"[{record.levelname}] [{module}] {message}"
        if excText:
            fullText += f"\n{excText}"

        MAX_MESSAGE_LENGTH = 2000
        if len(fullText) > MAX_MESSAGE_LENGTH:
            fullText = fullText[: MAX_MESSAGE_LENGTH - 20] + "\n...[truncated]"

        payload = {"content": fullText}

        try:
            discordExecutor.submit(
                requests.post,
                Config.DISCORD.WEBHOOK_URL,
                json=payload,
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"Discord webhook failed: {e}")


def setupDiscordHandler():
    if Config.DISCORD.ENABLED and Config.DISCORD.WEBHOOK_URL:
        logging.getLogger().addHandler(DiscordHandler())


setupLogging()
setupDiscordHandler()
