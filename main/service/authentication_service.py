import os
from config import Config

from starlette.middleware.sessions import SessionMiddleware

from main.utils.service_manager import ServiceManager
from main.controller.authentication_controller import router as authenticationRouter


class AuthenticationService:
    @staticmethod
    def initialize(port: int):
        service = ServiceManager.getApp(port)

        service.add_middleware(
            SessionMiddleware, secret_key=Config.USER["SESSION_SECRET_KEY"], same_site="lax", https_only=False
        )
        service.include_router(authenticationRouter)
