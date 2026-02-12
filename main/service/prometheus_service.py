from main.utils.service_manager import ServiceManager
from main.controller.prometheus_controller import router as prometheus_router

class PrometheusService:
    @staticmethod
    def initialize(port: int):
        app = ServiceManager.getApp(port)
        app.include_router(prometheus_router)