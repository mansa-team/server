import logging

from pydantic import BaseModel
from sqlalchemy.orm import Session

from main.models.wallet import Wallet

logger = logging.getLogger(__name__)


class WalletCreate(BaseModel):
    name: str


class WalletsManager:
    @classmethod
    def getMyWallet(cls, db: Session, userId: int) -> Wallet:
        wallet = db.query(Wallet).filter(Wallet.userId == userId).first()
        if wallet is None:
            wallet = Wallet(userId=userId, name="Carteira")
            db.add(wallet)
            db.commit()
            db.refresh(wallet)
        return wallet

    @classmethod
    def createWallet(cls, db: Session, userId: int, name: str) -> Wallet:
        existing = db.query(Wallet).filter(Wallet.userId == userId).first()
        if existing is not None:
            logger.info("Wallet already exists for user, returning it")
            return existing
        wallet = Wallet(userId=userId, name=name)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        return wallet

    @classmethod
    # Kept: manager layer API used by wallet_controller (Controller→Service boundary) — keep.
    def listWallets(cls, db: Session, userId: int) -> list[Wallet]:
        return db.query(Wallet).filter(Wallet.userId == userId).all()
