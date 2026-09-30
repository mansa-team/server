import logging

from fastapi import APIRouter, Depends
from fastapi.responses import ORJSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import getSession
from main.app.wallet.auth import requireWalletUser
from main.service import wallet_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wallet", tags=["wallet"])


class WalletCreate(BaseModel):
    name: str


@router.post("/wallets", response_class=ORJSONResponse, status_code=201)
def create_wallet_route(
    payload: WalletCreate,
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    wallet = wallet_service.create_wallet(db, user["userId"], payload.name)
    return {"walletId": wallet.walletId, "name": wallet.name}


@router.get("/wallets", response_class=ORJSONResponse)
def list_wallets_route(
    user: dict = Depends(requireWalletUser),
    db: Session = Depends(getSession),
):
    return [
        {"walletId": walletItem.walletId, "name": walletItem.name, "lastRecalc": walletItem.lastRecalc}
        for walletItem in wallet_service.list_wallets(db, user["userId"])
    ]
