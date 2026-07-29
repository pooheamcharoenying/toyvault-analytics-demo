"""LINE identity: bind a LINE user id to a ToyVault account, and short-lived
one-time link codes to establish that binding securely.

Binding flow: the signed-in user generates a link code in the web app and sends it
to the LINE bot; the bot consumes the code and records line_user_id -> username.
An unbound LINE user gets nothing but the instructions to link (no fallback
account, matching the auth model).

Collections (app-owned, never touched by the daily sync):
  line_bindings    { _id: line_user_id, username, thread_id, bound_at }
  line_link_codes  { _id: code, username, exp }
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger(__name__)

_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # unambiguous
_CODE_TTL_MINUTES = 15


def _db():
    from app.utils import mongo_store as ms
    return ms.get_db()


def _now():
    return datetime.now(timezone.utc)


# --- link codes ------------------------------------------------------------
def create_link_code(username: str) -> Optional[str]:
    db = _db()
    if db is None:
        return None
    code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(6))
    db["line_link_codes"].replace_one(
        {"_id": code},
        {"_id": code, "username": username, "exp": _now() + timedelta(minutes=_CODE_TTL_MINUTES)},
        upsert=True,
    )
    return code


def consume_link_code(code: str) -> Optional[str]:
    """Return the username for a valid, unexpired code and delete it; else None."""
    db = _db()
    if db is None:
        return None
    doc = db["line_link_codes"].find_one_and_delete({"_id": (code or "").strip().upper()})
    if not doc:
        return None
    exp = doc.get("exp")
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp and exp < _now():
        return None
    return doc.get("username")


# --- bindings --------------------------------------------------------------
def bind(line_user_id: str, username: str) -> None:
    db = _db()
    if db is None:
        return
    db["line_bindings"].update_one(
        {"_id": line_user_id},
        {"$set": {"username": username, "bound_at": _now()}},
        upsert=True,
    )


def get_username(line_user_id: str) -> Optional[str]:
    db = _db()
    if db is None:
        return None
    doc = db["line_bindings"].find_one({"_id": line_user_id}, {"username": 1})
    return doc.get("username") if doc else None


def get_or_create_thread(line_user_id: str, username: str) -> Optional[str]:
    """One persistent thread per LINE user, so LINE conversations have memory and
    also appear in the user's web thread list."""
    from app.assistant import threads
    db = _db()
    if db is None:
        return None
    doc = db["line_bindings"].find_one({"_id": line_user_id}, {"thread_id": 1})
    tid = doc.get("thread_id") if doc else None
    if tid and threads.owns(username, tid):
        return tid
    tid = threads.create(username, "LINE chat")
    db["line_bindings"].update_one({"_id": line_user_id}, {"$set": {"thread_id": tid}}, upsert=True)
    return tid


def reset_thread(line_user_id: str, username: str) -> Optional[str]:
    """Start a fresh LINE conversation: point the binding at a brand-new empty
    thread so the next message has no prior context. The old thread is kept (its
    history stays in the web thread list); we just stop using it."""
    from app.assistant import threads
    db = _db()
    if db is None:
        return None
    tid = threads.create(username, "LINE chat")
    db["line_bindings"].update_one({"_id": line_user_id}, {"$set": {"thread_id": tid}}, upsert=True)
    return tid
