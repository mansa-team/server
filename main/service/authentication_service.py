from main.utils.service_manager import ServiceManager
from main.controller.authentication_controller import router as authenticationRouter

class AuthenticationService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(authenticationRouter)