import logging
from datetime import date as dateType
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.orm import Session

from main.app.stocks_api.sync_cache import MISS, syncCacheGet, syncCacheSet
from main.app.wallet.entries import EntriesManager
from main.app.wallet.positions import PositionsManager
from main.app.wallet.wallets import WalletsManager
from main.models.wallet import Earning, Holding, Transaction

logger = logging.getLogger(__name__)

IR_RATE = {"Div": 0.0, "JSCP": 0.15, "RendTributado": 0.15}

TIPO_MAP = {
    "Dividendo": "Div",
    "JCP": "JSCP",
    "Juros Sobre Capital Proprio": "JSCP",
    "Rend. Tributado": "RendTributado",
}


class EarningsSync(BaseModel):
    wallet_id: int


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
    def autoSyncKey(cls, walletId: int) -> str:
        return f"wallet:earnings:autosync:{walletId}"

    @classmethod
    def maybeAutoSync(cls, db: Session, walletId: int, userId: int) -> None:
        # Sync-on-read with TTL: fresh without hammering the stocks API
        # (per-wallet marker; short negative cache on failure). Never raises.
        try:
            if syncCacheGet(cls.autoSyncKey(walletId)) is not MISS:
                return
            cls.syncEarnings(db, walletId, userId)
            syncCacheSet(cls.autoSyncKey(walletId), 1, cls.AUTO_SYNC_TTL)
        except Exception:
            logger.warning("earnings autosync failed for wallet %s", walletId, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            try:
                syncCacheSet(cls.autoSyncKey(walletId), 1, cls.AUTO_SYNC_NEG_TTL)
            except Exception:
                pass

    @classmethod
    def syncEarnings(cls, db: Session, walletId: int, userId: int) -> dict:
        WalletsManager.getWallet(db, walletId, userId)

        today = dateType.today()
        accrued = 0
        skippedUnknown: list[str] = []

        holdings = db.query(Holding).filter(Holding.walletId == walletId).all()
        for holding in holdings:
            if float(holding.quantity) <= 0:
                continue

            holdingTicker = str(holding.ticker)

            ledgerEntries = (
                db.query(Transaction)
                .filter(Transaction.walletId == walletId, Transaction.ticker == holdingTicker)
                .order_by(Transaction.date, Transaction.entryId)
                .all()
            )

            for record in PositionsManager.fetchMarketDividends(holdingTicker):
                label = str(record.get("TIPO PROVENTO"))
                kind = TIPO_MAP.get(label)

                if kind is None:
                    if label not in skippedUnknown:
                        skippedUnknown.append(label)
                    continue

                try:
                    exDate = datetime.strptime(record["DATA COM"], "%d-%m-%Y").date()
                    payDate = datetime.strptime(record["DATA PAGAMENTO"], "%d-%m-%Y").date()
                    perShare = float(record["VALOR AJUSTADO"])
                except Exception:
                    continue

                quantityAtEx = EntriesManager.positionAtDate(ledgerEntries, exDate)
                if quantityAtEx <= 0:
                    continue

                existing = (
                    db.query(Earning)
                    .filter(
                        Earning.walletId == walletId,
                        Earning.ticker == holdingTicker,
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
                    ticker=holdingTicker,
                    kind=kind,
                    exDate=exDate,
                    payDate=payDate,
                    gross=gross,
                    netIrAdjusted=gross * (1 - IR_RATE[kind]),
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
    def listEarnings(cls, db: Session, walletId: int, userId: int, status: str | None = None) -> list[Earning]:
        WalletsManager.getWallet(db, walletId, userId)
        cls.maybeAutoSync(db, walletId, userId)
        query = db.query(Earning).filter(Earning.walletId == walletId)

        if status is not None:
            query = query.filter(Earning.status == status)

        return query.order_by(Earning.exDate, Earning.earningId).all()
