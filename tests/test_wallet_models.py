from main.models.base import Base
from main.models.wallet import Holding, Snapshot, Target, Transaction, Wallet


def test_wallet_tables_create_and_round_trip(dbSession):
    wallet = Wallet(userId=1, name="Principal")
    dbSession.add(wallet)
    dbSession.commit()
    assert wallet.walletId == 1
    holding = Holding(
        walletId=wallet.walletId,
        assetType="Stock",
        ticker="PETR4",
        quantity=10,
        avgPrice=28.5,
    )
    dbSession.add(holding)
    dbSession.commit()
    assert holding.holdingId == 1
    assert holding.rating is None
