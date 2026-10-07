from typing import Any, Optional

from config import SessionLocal
from sqlalchemy.orm import Session


def popAuthSession(args: dict) -> tuple[Any, Optional[Session], bool, Optional[dict]]:
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
