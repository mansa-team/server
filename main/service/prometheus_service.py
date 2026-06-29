from main.utils.service_manager import ServiceManager
from main.controller.prometheus_controller import router as prometheusRouter
from main.utils.models.loader import getEmbeddingModel


class PrometheusService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(prometheusRouter)

        getEmbeddingModel()
