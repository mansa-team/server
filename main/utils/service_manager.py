from imports import *

class ServiceManager:
    _instances = {}

    @classmethod
    def getApp(cls, port: int) -> FastAPI:
        if port not in cls._instances:
            app = FastAPI(title=f"Mansa Service {port}")
            app.add_middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            
            cls._instances[port] = app
        return cls._instances[port]

    @classmethod
    def runAll(cls):
        for port, app in cls._instances.items():
            thread = threading.Thread(
                target=lambda: uvicorn.run(app, host="0.0.0.0", port=port, log_level="error"),
                daemon=True
            )
            thread.start()

            if Config.DEBUG_MODE == "TRUE": print(f"Service running on port {port}")