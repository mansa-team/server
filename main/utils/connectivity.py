from config import Config, engine, stocksEngine
from main.utils.util import log

import time
import logging
from requests.exceptions import ConnectionError, Timeout, RequestException
from sqlalchemy import text
import requests

logger = logging.getLogger(__name__)

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
            log("db", f"USER DB connected ({latency:.2f}ms)")
            userDb = True
        except (ConnectionError, Timeout) as e:
            log("db", f"USER DB connection failed: {e}")
        except Exception as e:
            log("db", f"USER DB unexpected error: {e}")
    else:
        log("db", "USER DB engine not initialized!")

    if stocksEngine:
        try:
            startTime = time.time()
            with stocksEngine.connect() as connection:
                connection.execute(text("SELECT 1"))
                connection.commit()
            latency = (time.time() - startTime) * 1000
            log("db", f"STOCKS DB connected ({latency:.2f}ms)")
            stocksDb = True
        except (ConnectionError, Timeout) as e:
            log("db", f"STOCKS DB connection failed: {e}")
        except Exception as e:
            log("db", f"STOCKS DB unexpected error: {e}")
    else:
        log("db", "STOCKS DB engine not initialized!")

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
        elif service == "PROMETHEUS":
            prefix = "prometheus"
        else:
            prefix = service.lower()

        startTime = time.time()
        response = requests.get(f"http://{host}:{port}/{prefix}/health", timeout=5)
        latency = (time.time() - startTime) * 1000

        if response.status_code == 200:
            log("service", f"{service} connected ({latency:.2f}ms)")
            return True
    except (ConnectionError, Timeout, RequestException) as e:
        log("service", f"{service} connection failed: {e}")
        return False
    except Exception as e:
        log("service", f"{service} unexpected error: {e}")
        return False