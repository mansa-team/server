from imports import *
from main.utils.util import log

import threading
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

class ServiceManager:
    _instances = {}

    @classmethod
    def getApp(cls, port: int) -> FastAPI:
        if port not in cls._instances:
            app = FastAPI(title=f"Mansa Service {port}")
            app.add_middleware(
                CORSMiddleware,
                allow_origin_regex="https?://.*",
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            cls._instances[port] = app
        return cls._instances[port]

    @classmethod
    def runAll(cls):
        logLevel = "error" if Config.DEBUG_MODE == "TRUE" else "critical"

        for port, app in cls._instances.items():
            thread = threading.Thread(
                target=lambda p=port, a=app: uvicorn.run(a, host="0.0.0.0", port=p, log_level=logLevel),
                daemon=True
            )
            thread.start()

            if Config.DEBUG_MODE == "TRUE": print(f"Service running on port {port}")