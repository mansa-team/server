from datetime import date

from sqlalchemy import Numeric

from main.models.base import Base
from main.models.wallet import Earning, Holding, Target, Transaction, Wallet


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


def test_holding_rating_keeps_decimal_scores(dbSession):
    wallet = Wallet(userId=1, name="W")
    dbSession.add(wallet)
    dbSession.commit()
    holding = Holding(
        walletId=wallet.walletId,
        assetType="ACOES",
        ticker="PETR4",
        quantity=10,
        avgPrice=28.5,
        rating=72.5,
    )
    dbSession.add(holding)
    dbSession.commit()
    dbSession.expire_all()
    stored = dbSession.query(Holding).filter(Holding.holdingId == holding.holdingId).first()
    assert stored.rating == 72.5


def test_holding_rating_column_is_decimal_capable():
    # MySQL SMALLINT rounds 72.5 to an integer; the column must hold decimal scores.
    assert isinstance(Holding.__table__.c.rating.type, Numeric)


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
