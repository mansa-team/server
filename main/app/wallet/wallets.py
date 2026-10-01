import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from main.models.wallet import Wallet

logger = logging.getLogger(__name__)


def getOwnedWallet(db: Session, walletId: int, userId: int):
    from main.app.wallet.auth import requireWalletOwnership

    wallet = db.query(Wallet).filter(Wallet.walletId == walletId).first()
    if wallet is None:
        raise HTTPException(status_code=404, detail="wallet not found")
    requireWalletOwnership(int(wallet.userId), {"userId": userId})
    return wallet


def createWallet(db: Session, userId: int, name: str) -> Wallet:
    wallet = Wallet(userId=userId, name=name)
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def listWallets(db: Session, userId: int) -> list[Wallet]:
    return db.query(Wallet).filter(Wallet.userId == userId).all()
