import logging

from main.controller.wallet_controller import router as walletRouter
from main.utils.service_manager import getApp

logger = logging.getLogger(__name__)


class WalletService:
    @staticmethod
    def initialize(port: int):
        service = getApp(port)
        service.include_router(walletRouter)
