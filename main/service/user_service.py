from main.utils.service_manager import ServiceManager
from main.controller.user_controller import router as userRouter

class UserService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)
        service.include_router(userRouter)