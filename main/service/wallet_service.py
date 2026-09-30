import logging

from sqlalchemy.orm import Session

from main.models.wallet import Wallet

logger = logging.getLogger(__name__)


def create_wallet(db: Session, userId: int, name: str) -> Wallet:
    wallet = Wallet(userId=userId, name=name)
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


def list_wallets(db: Session, userId: int) -> list[Wallet]:
    return db.query(Wallet).filter(Wallet.userId == userId).all()
