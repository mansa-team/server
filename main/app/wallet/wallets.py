import logging

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from main.models.wallet import Wallet

logger = logging.getLogger(__name__)


class WalletCreate(BaseModel):
    name: str


class WalletsManager:
    @classmethod
    def getWallet(cls, db: Session, walletId: int, userId: int):
        wallet = db.query(Wallet).filter(Wallet.walletId == walletId, Wallet.userId == userId).first()
        if wallet is None:
            raise HTTPException(status_code=404, detail="wallet not found")
        return wallet

    @classmethod
    def createWallet(cls, db: Session, userId: int, name: str) -> Wallet:
        wallet = Wallet(userId=userId, name=name)
        db.add(wallet)
        db.commit()
        db.refresh(wallet)
        return wallet

    @classmethod
    def listWallets(cls, db: Session, userId: int) -> list[Wallet]:
        return db.query(Wallet).filter(Wallet.userId == userId).all()
