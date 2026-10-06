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
    def getMyWallet(cls, db: Session, userId: int) -> Wallet:
        """Single-wallet lookup-by-userId with get-or-create.

        The wallet id is never accepted from the client: callers resolve it
        here from the authenticated user, then keep getWallet as a
        defense-in-depth ownership assert on the resolved id.
        """
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
    def listWallets(cls, db: Session, userId: int) -> list[Wallet]:
        return db.query(Wallet).filter(Wallet.userId == userId).all()
