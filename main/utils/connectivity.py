import logging
import time
from requests.exceptions import ConnectionError, Timeout, RequestException
from main.utils.http_session import getSession
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from config import Config, engine, stocksEngine

logger = logging.getLogger(__name__)


def checkSingleDb(dbEngine, name):
    if not dbEngine:
        return {"status": "not_configured"}
    try:
        startTime = time.time()
        with dbEngine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (time.time() - startTime) * 1000
        pool = dbEngine.pool
        return {
            "status": "connected",
            "latency_ms": round(latency, 2),
            "pool": {
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "checked_out": pool.checkedout(),
                "overflow": pool.overflow(),
            },
        }
    except OperationalError as e:
        return {"status": "error", "error": str(e)}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def checkMySqlConnection():
    results = {
        "user_db": checkSingleDb(engine, "user_db"),
        "stocks_db": checkSingleDb(stocksEngine, "stocks_db"),
    }
    return results["user_db"]["status"] == "connected" and results["stocks_db"]["status"] == "connected"


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
