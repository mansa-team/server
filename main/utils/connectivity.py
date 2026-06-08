import logging
import time
from requests.exceptions import ConnectionError, Timeout, RequestException
from main.utils.http_session import getSession
from sqlalchemy import text

from config import Config, engine, stocksEngine

logger = logging.getLogger(__name__)

# Use thread-safe session (via getSession()) for all HTTP calls.


def checkMySqlConnection():
    stocksDb = False
    userDb = False
    if engine:
        try:
            startTime = time.time()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.commit()
            latency = (time.time() - startTime) * 1000
            logger.info(f"USER DB connected ({latency:.2f}ms)")
            userDb = True
        except (ConnectionError, Timeout) as e:
            logger.error(f"USER DB connection failed: {e}")
        except Exception as e:
            logger.error(f"USER DB unexpected error: {e}")
    else:
        logger.warning("USER DB engine not initialized!")

    if stocksEngine:
        try:
            startTime = time.time()
            with stocksEngine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.commit()
            latency = (time.time() - startTime) * 1000
            logger.info(f"STOCKS DB connected ({latency:.2f}ms)")
            stocksDb = True
        except (ConnectionError, Timeout) as e:
            logger.error(f"STOCKS DB connection failed: {e}")
        except Exception as e:
            logger.error(f"STOCKS DB unexpected error: {e}")
    else:
        logger.warning("STOCKS DB engine not initialized!")

    return userDb and stocksDb


def checkServiceConnection(service: str):
    try:
        serviceConfig: dict[str, str] | None = getattr(Config, service, None)
        if not serviceConfig:
            return False
        host = serviceConfig["HOST"]
        port = serviceConfig["PORT"]

        if service == "STOCKS_API":
            prefix = "stocks"
        else:
            prefix = service.lower()

        startTime = time.time()
        response = getSession().get(f"http://{host}:{port}/{prefix}/health", timeout=5)
        latency = (time.time() - startTime) * 1000

        if response.status_code == 200:
            logger.info(f"{service} connected ({latency:.2f}ms)")
            return True
    except (ConnectionError, Timeout, RequestException) as e:
        logger.error(f"{service} connection failed: {e}")
        return False
    except Exception as e:
        logger.error(f"{service} unexpected error: {e}")
        return False
