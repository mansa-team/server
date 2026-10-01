from sqlalchemy import (
    Column,
    Date,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    TIMESTAMP,
    UniqueConstraint,
    func,
)

from main.models.base import Base


class Wallet(Base):
    __tablename__ = "wallets"

    walletId = Column(Integer, primary_key=True, autoincrement=True)
    userId = Column(Integer, ForeignKey("users.userId", ondelete="RESTRICT"), nullable=False, index=True)
    name = Column(String(120), nullable=False)
    lastRecalc = Column(TIMESTAMP, nullable=True)
    createdAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)


class Holding(Base):
    __tablename__ = "holdings"

    holdingId = Column(Integer, primary_key=True, autoincrement=True)
    walletId = Column(Integer, ForeignKey("wallets.walletId", ondelete="RESTRICT"), nullable=False, index=True)
    assetType = Column(String(20), nullable=False)
    ticker = Column(String(20), nullable=False, index=True)
    tickerName = Column(String(120), nullable=True)
    quantity = Column(Numeric(18, 8), nullable=False)
    avgPrice = Column(Numeric(18, 6), nullable=False)
    percentIdeal = Column(Numeric(5, 2), nullable=True)
    rating = Column(SmallInteger, nullable=True)
    updatedAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)

    __table_args__ = (UniqueConstraint("walletId", "ticker", name="uq_holdings_wallet_ticker"),)


class Transaction(Base):
    __tablename__ = "transactions"

    entryId = Column(Integer, primary_key=True, autoincrement=True)
    walletId = Column(Integer, ForeignKey("wallets.walletId", ondelete="RESTRICT"), nullable=False, index=True)
    side = Column(Enum("Compra", "Venda", name="entry_side"), nullable=False)  # type: ignore[var-annotated]
    assetType = Column(String(20), nullable=False)
    ticker = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    price = Column(Numeric(18, 6), nullable=False)
    costs = Column(Numeric(18, 2), nullable=False, default=0)
    createdAt = Column(TIMESTAMP, server_default=func.current_timestamp(), nullable=False)


class Target(Base):
    __tablename__ = "targets"

    targetId = Column(Integer, primary_key=True, autoincrement=True)
    walletId = Column(Integer, ForeignKey("wallets.walletId", ondelete="RESTRICT"), nullable=False, index=True)
    keyKind = Column(Enum("ticker", "group", name="target_key_kind"), nullable=False)  # type: ignore[var-annotated]
    keyValue = Column(String(40), nullable=False)
    percentIdeal = Column(Numeric(5, 2), nullable=False)

    __table_args__ = (UniqueConstraint("walletId", "keyKind", "keyValue", name="uq_targets_wallet_key"),)


class Snapshot(Base):
    __tablename__ = "snapshots"

    snapshotId = Column(Integer, primary_key=True, autoincrement=True)
    walletId = Column(Integer, ForeignKey("wallets.walletId", ondelete="RESTRICT"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    applied = Column(Numeric(18, 2), nullable=False)
    equity = Column(Numeric(18, 2), nullable=False)
    variation = Column(Numeric(18, 2), nullable=False)
    profitTwr = Column(Numeric(10, 6), nullable=True)
    profitAmount = Column(Numeric(18, 2), nullable=False)
    profitTwr12m = Column(Numeric(10, 6), nullable=True)
    profitTwr12mAmount = Column(Numeric(18, 2), nullable=False)

    __table_args__ = (UniqueConstraint("walletId", "date", name="uq_snapshots_wallet_date"),)


class Earning(Base):
    __tablename__ = "earnings"

    earningId = Column(Integer, primary_key=True, autoincrement=True)
    walletId = Column(Integer, ForeignKey("wallets.walletId", ondelete="RESTRICT"), nullable=False, index=True)
    ticker = Column(String(20), nullable=False, index=True)
    kind = Column(Enum("Div", "JSCP", "RendTributado", name="earning_kind"), nullable=False)  # type: ignore[var-annotated]
    exDate = Column(Date, nullable=False)
    payDate = Column(Date, nullable=False)
    gross = Column(Numeric(18, 2), nullable=False)
    netIrAdjusted = Column(Numeric(18, 2), nullable=False)
    status = Column(Enum("A Receber", "Recebido", name="earning_status"), nullable=False, index=True)  # type: ignore[var-annotated]

    __table_args__ = (UniqueConstraint("walletId", "ticker", "exDate", "kind", name="uq_earnings_accrual"),)
