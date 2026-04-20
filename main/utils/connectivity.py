from config import Config, engine, stocksEngine
from main.utils.util import log

import time
from sqlalchemy import text
import requests

def checkMYSQLConnection():
    stocksDB = False
    userDB = False
    if engine:
        try:
            startTime = time.time()
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            latency = (time.time() - startTime) * 1000
            log("db", f"USER DB connected ({latency:.2f}ms)")
            userDB = True
        except Exception as e:
            log("db", f"USER DB connection failed: {e}")
    else:
        log("db", "USER DB engine not initialized!")

    if stocksEngine:
        try:
            startTime = time.time()
            with stocksEngine.connect() as connection:
                connection.execute(text("SELECT 1"))
            latency = (time.time() - startTime) * 1000
            log("db", f"STOCKS DB connected ({latency:.2f}ms)")
            stocksDB = True
        except Exception as e:
            log("db", f"STOCKS DB connection failed: {e}")
    else:
        log("db", "STOCKS DB engine not initialized!")

    return userDB and stocksDB


def checkServiceConnection(service: str):
    try:
        serviceConfig: dict[str, str] | None = getattr(Config, service, None)
        if not serviceConfig:
            return False
        host = serviceConfig["HOST"]
        port = serviceConfig["PORT"]

        if service == "STOCKS_API":
            prefix = "stocks"
        if service == "PROMETHEUS":
            prefix = "prometheus"

        startTime = time.time()
        response = requests.get(f"http://{host}:{port}/{prefix}/health", timeout=5)
        latency = (time.time() - startTime) * 1000

        if response.status_code == 200:
            log("service", f"{service} connected ({latency:.2f}ms)")

            return True
    except Exception as e:
        log("service", f"{service} connection failed: {e}\nDue to this issue the server couldn't start.")

        return False