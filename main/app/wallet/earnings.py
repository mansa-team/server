"""Dividend accruals derived from the transaction ledger.

Source-of-truth rule (reviewer #1/#11): discovery iterates tickers that
appear in the Transaction ledger — never current holdings — and entitlement
replays the ledger up to each ex-date (position-at-date via
``EntriesManager.applyEntries``). A user who owned shares on ex-date but
fully liquidated before sync (or before pay-date) still accrues.

Accrual semantics: one Earning per (wallet, ticker, exDate, kind)
(``uq_earnings_accrual``); multiple market rows sharing (exDate, kind) are
installments aggregated with payDate = latest. ``gross`` = perShare x
qtyAtEx; ``netIrAdjusted`` = gross x (1 - IR) with Div 0%, JSCP and
RendTributado 15%. Status flips to Recebido once payDate passes (re-checked
every sync for pending rows). Unknown TIPO PROVENTO labels are skipped and
reported, never stored.

Money math is :class:`~decimal.Decimal`; ``float`` only at serialization.
"""

import logging
from datetime import date as dateType
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import requests
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from main.utils.sync_cache import MISS, syncCacheGet, syncCacheSet
from main.app.wallet.entries import EntriesManager, toDecimal
from main.app.wallet.positions import PositionsManager
from main.models.wallet import Earning, Transaction, Wallet

logger = logging.getLogger(__name__)

IR_RATE = {"Div": Decimal("0"), "JSCP": Decimal("0.15"), "RendTributado": Decimal("0.15")}

TIPO_MAP = {
    "Dividendo": "Div",
    "JCP": "JSCP",
    "Juros Sobre Capital Proprio": "JSCP",
    "Rend. Tributado": "RendTributado",
}

# Reviewer #8: only genuine data-source failures degrade (autosync is
# best-effort); programming errors propagate. Cache-set failures degrade
# narrowly too — a failed timestamp write must not mask the sync result.
SYNC_ERRORS = (
    requests.exceptions.RequestException,
    ValueError,
    KeyError,
    TypeError,
    AttributeError,
    IndexError,
    SQLAlchemyError,
)
CACHE_ERRORS = (RuntimeError, OSError, ValueError)


# Kept: public API serialization used by wallet_controller — keep.
def serialize_earning(earning) -> dict:
    return {
        "ticker": earning.ticker,
        "kind": earning.kind,
        "gross": float(earning.gross),
        "net_ir_adjusted": float(earning.netIrAdjusted),
        "status": earning.status,
    }


class EarningsManager:
    AUTO_SYNC_TTL = "6h"
    AUTO_SYNC_NEG_TTL = "5m"

    @classmethod
    def maybeAutoSync(cls, db: Session, wallet: Wallet) -> None:
        try:
            if syncCacheGet(f"wallet:earnings:autosync:{wallet.userId}") is not MISS:
                return
            result = cls.syncEarnings(db, wallet)
            ttl = cls.AUTO_SYNC_TTL
            walletId = int(wallet.walletId)
            if (
                result["accrued"] == 0
                and db.query(Transaction).filter(Transaction.walletId == walletId).count() > 0
                and db.query(Earning).filter(Earning.walletId == walletId).count() == 0
            ):
                ttl = cls.AUTO_SYNC_NEG_TTL
            syncCacheSet(f"wallet:earnings:autosync:{wallet.userId}", 1, ttl)
        except SYNC_ERRORS:
            logger.warning("earnings autosync failed for wallet %s", wallet.walletId, exc_info=True)
            try:
                db.rollback()
            except SQLAlchemyError:
                pass
            try:
                syncCacheSet(f"wallet:earnings:autosync:{wallet.userId}", 1, cls.AUTO_SYNC_NEG_TTL)
            except CACHE_ERRORS:
                pass

    @classmethod
    def syncEarnings(cls, db: Session, wallet: Wallet) -> dict:
        """Accrue earnings for every ledger ticker with a position on ex-date."""
        walletId = int(wallet.walletId)

        today = dateType.today()
        accrued = 0
        skippedUnknown: list[str] = []

        tickerRows: list[Any] = db.query(Transaction.ticker).filter(Transaction.walletId == walletId).distinct().all()
        ledgerTickers: list[str] = sorted({str(ledgerTicker) for (ledgerTicker,) in tickerRows})
        for ledgerTicker in ledgerTickers:
            ledgerEntries = (
                db.query(Transaction)
                .filter(Transaction.walletId == walletId, Transaction.ticker == ledgerTicker)
                .order_by(Transaction.date, Transaction.entryId)
                .all()
            )

            accruals: dict[tuple, list[tuple]] = {}
            for record in PositionsManager.fetchMarketDividends(ledgerTicker):
                label = str(record.get("TIPO PROVENTO"))
                kind = TIPO_MAP.get(label)

                if kind is None:
                    if label not in skippedUnknown:
                        skippedUnknown.append(label)
                    continue

                try:
                    exDate = datetime.strptime(record["DATA COM"], "%d-%m-%Y").date()
                    payDate = datetime.strptime(record["DATA PAGAMENTO"], "%d-%m-%Y").date()
                    perShare = toDecimal(record["VALOR AJUSTADO"])
                except (ValueError, KeyError, TypeError, AttributeError, InvalidOperation):
                    continue

                key = (exDate, kind)
                installment = (payDate, perShare)
                if installment not in accruals.setdefault(key, []):
                    accruals[key].append(installment)

            for (exDate, kind), installments in accruals.items():
                payDate = max(pay for pay, _ in installments)
                perShare = sum((share for _, share in installments), Decimal(0))

                # Position-at-date: replay only entries on/before ex-date, so
                # post-ex sells (even full liquidation) keep the entitlement,
                # while pre-ex sells reduce it.
                quantityAtEx, _ = EntriesManager.applyEntries(
                    Decimal(0), Decimal(0), [entry for entry in ledgerEntries if str(entry.date) <= exDate.isoformat()]
                )
                if quantityAtEx <= 0:
                    continue

                existing = (
                    db.query(Earning)
                    .filter(
                        Earning.walletId == walletId,
                        Earning.ticker == ledgerTicker,
                        Earning.exDate == exDate,
                        Earning.kind == kind,
                    )
                    .first()
                )

                if existing is not None:
                    continue

                gross = perShare * quantityAtEx
                earning = Earning(
                    walletId=walletId,
                    ticker=ledgerTicker,
                    kind=kind,
                    exDate=exDate,
                    payDate=payDate,
                    gross=gross,
                    netIrAdjusted=gross * (Decimal(1) - IR_RATE[kind]),
                    status="Recebido" if payDate <= today else "A Receber",
                )

                db.add(earning)

                accrued += 1
        transitioned = 0

        pending = db.query(Earning).filter(Earning.walletId == walletId, Earning.status == "A Receber").all()
        for earning in pending:
            if str(earning.payDate) <= today.isoformat():
                earning.status = "Recebido"  # type: ignore[assignment]
                transitioned += 1

        db.commit()

        return {"accrued": accrued, "transitioned": transitioned, "skipped_unknown": skippedUnknown}

    @classmethod
    def listEarnings(cls, db: Session, wallet: Wallet) -> list[Earning]:
        walletId = int(wallet.walletId)
        cls.maybeAutoSync(db, wallet)
        query = db.query(Earning).filter(Earning.walletId == walletId)

        return query.order_by(Earning.exDate, Earning.earningId).all()
