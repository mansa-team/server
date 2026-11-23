from main.controller.authentication_controller import router as authenticationRouter
from main.utils.service_manager import getApp


class AuthenticationService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(authenticationRouter)
