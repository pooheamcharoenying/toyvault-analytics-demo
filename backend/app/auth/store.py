"""The app-owned ``users`` collection — admin-managed accounts.

Passwords are **bcrypt-hashed**; the plaintext is never stored or logged. One
document per username (lower-cased and used as ``_id``). Authored by admins and
never touched by the data pipeline.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from passlib.context import CryptContext

logger = logging.getLogger(__name__)

COLLECTION = "users"
_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _coll():
    from app.utils import mongo_store as ms
    db = ms.get_db()
    return db[COLLECTION] if db is not None else None


def is_available() -> bool:
    return _coll() is not None


def _norm(username: str) -> str:
    return str(username or "").strip().lower()


def get_user(username: str) -> Optional[dict]:
    c = _coll()
    if c is None:
        return None
    return c.find_one({"_id": _norm(username)})


def count_users() -> int:
    c = _coll()
    return c.count_documents({}) if c is not None else 0


def verify_credentials(username: str, password: str) -> Optional[Dict[str, Any]]:
    """Return the user's public identity on success, else None. Never reveals
    whether it was the username or the password that was wrong."""
    u = get_user(username)
    if not u or not u.get("active", True):
        return None
    try:
        if not _pwd.verify(password or "", u.get("password_hash", "")):
            return None
    except Exception:
        return None
    return {"username": u["_id"], "display_name": u.get("display_name") or u["_id"],
            "role": u.get("role", "user")}


def create_user(username: str, password: str, display_name: Optional[str] = None,
                role: str = "user") -> str:
    """Create or update a user (upsert). Raises ValueError on bad input."""
    uname = _norm(username)
    if not uname:
        raise ValueError("username is required")
    if not password or len(password) < 6:
        raise ValueError("password must be at least 6 characters")
    if role not in ("user", "admin"):
        raise ValueError("role must be 'user' or 'admin'")
    c = _coll()
    if c is None:
        raise RuntimeError("MongoDB is not configured; cannot create users")
    now = datetime.now(timezone.utc)
    c.update_one(
        {"_id": uname},
        {"$set": {"password_hash": _pwd.hash(password),
                  "display_name": display_name or username, "role": role,
                  "active": True, "updated_at": now},
         "$setOnInsert": {"created_at": now}},
        upsert=True,
    )
    logger.info("user '%s' (role=%s) created/updated", uname, role)
    return uname


def change_password(username: str, current_password: str, new_password: str) -> None:
    """Verify the user's current password, then set a new one. Raises ValueError
    (surfaced as 422) on a wrong current password or a too-short new one."""
    u = get_user(username)
    if not u:
        raise ValueError("User not found.")
    try:
        ok = _pwd.verify(current_password or "", u.get("password_hash", ""))
    except Exception:
        ok = False
    if not ok:
        raise ValueError("Current password is incorrect.")
    if not new_password or len(new_password) < 8:
        raise ValueError("New password must be at least 8 characters.")
    _coll().update_one({"_id": u["_id"]},
                       {"$set": {"password_hash": _pwd.hash(new_password),
                                 "updated_at": datetime.now(timezone.utc)}})


def set_active(username: str, active: bool) -> None:
    c = _coll()
    if c is not None:
        c.update_one({"_id": _norm(username)}, {"$set": {"active": bool(active)}})


def delete_user(username: str) -> None:
    c = _coll()
    if c is not None:
        c.delete_one({"_id": _norm(username)})


def list_users() -> List[Dict[str, Any]]:
    c = _coll()
    if c is None:
        return []
    return [{"username": u["_id"], "display_name": u.get("display_name") or u["_id"],
             "role": u.get("role", "user"), "active": u.get("active", True)}
            for u in c.find({}, {"password_hash": 0})]
