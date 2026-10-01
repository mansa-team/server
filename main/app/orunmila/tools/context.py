from typing import Any, Optional

from config import SessionLocal
from sqlalchemy.orm import Session


def popAuthSession(args: dict) -> tuple[Any, Optional[Session], bool, Optional[dict]]:
    """Shared auth-guard + own-SessionLocal convention every tool repeats.

    Returns (user, db, ownSession, error). When error is not None the caller
    must return it immediately. Otherwise the caller must release db via
    closeOwnSession when ownSession is True.
    """
    user = args.get("user")
    if not user:
        return None, None, False, {"error": "Authentication required"}
    db: Optional[Session] = args.get("db")
    ownSession = not db
    if ownSession:
        db = SessionLocal()
    return user, db, ownSession, None


def closeOwnSession(db: Optional[Session], ownSession: bool) -> None:
    if ownSession:
        db.close()  # type: ignore[union-attr]
