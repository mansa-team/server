from main.utils.service_manager import ServiceManager
from main.controller.auth_controller import router as auth_router 

class AuthService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(auth_router)