from datetime import date

from main.models.base import Base
from main.models.wallet import Earning, Holding, Snapshot, Target, Transaction, Wallet


def test_wallet_tables_create_and_round_trip(dbSession):
    wallet = Wallet(userId=1, name="Principal")
    dbSession.add(wallet)
    dbSession.commit()
    assert wallet.walletId == 1
    holding = Holding(
        walletId=wallet.walletId,
        assetType="ACOES",
        ticker="PETR4",
        quantity=10,
        avgPrice=28.5,
    )
    dbSession.add(holding)
    dbSession.commit()
    assert holding.holdingId == 1
    assert holding.rating is None


def test_earning_round_trip(dbSession):
    wallet = Wallet(userId=1, name="W")
    dbSession.add(wallet)
    dbSession.commit()
    row = Earning(
        walletId=wallet.walletId,
        ticker="PETR4",
        kind="JSCP",
        exDate=date(2026, 3, 1),
        payDate=date(2026, 4, 1),
        gross=10.0,
        netIrAdjusted=8.5,
        status="A Receber",
    )
    dbSession.add(row)
    dbSession.commit()
    assert row.earningId == 1
    assert row.netIrAdjusted == 8.5
