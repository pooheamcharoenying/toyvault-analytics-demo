"""Per-user chat threads — persistent conversation memory.

App-owned ``chat_threads`` collection (never touched by the daily SAP sync). One
document per thread; the messages live in an array inside it and every thread is
scoped to its owner (``user``), so a query without the right user never returns
another person's conversation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION = "chat_threads"
MAX_HISTORY = 24  # how many recent messages of context to feed the model


def _coll():
    from app.utils import mongo_store as ms
    db = ms.get_db()
    return db[COLLECTION] if db is not None else None


def is_available() -> bool:
    return _coll() is not None


def _now():
    return datetime.now(timezone.utc)


def title_from(text: str) -> str:
    t = " ".join((text or "").split())
    return (t[:48] + "…") if len(t) > 48 else (t or "New chat")


def create(user: str, title: str = "New chat") -> str:
    c = _coll()
    if c is None:
        raise RuntimeError("MongoDB is not configured; cannot create chat threads")
    tid = uuid.uuid4().hex
    c.insert_one({"_id": tid, "user": user, "title": (title or "New chat")[:80],
                  "messages": [], "created_at": _now(), "updated_at": _now()})
    return tid


def owns(user: str, tid: str) -> bool:
    c = _coll()
    return c is not None and c.count_documents({"_id": tid, "user": user}) > 0


def list_for(user: str) -> List[Dict[str, Any]]:
    """Thread summaries (no message bodies) for the sidebar, newest first."""
    c = _coll()
    if c is None:
        return []
    rows = c.aggregate([
        {"$match": {"user": user}},
        {"$project": {"title": 1, "updated_at": 1,
                      "message_count": {"$size": {"$ifNull": ["$messages", []]}}}},
        {"$sort": {"updated_at": -1}},
    ])
    return [{"thread_id": r["_id"], "title": r.get("title") or "New chat",
             "message_count": r.get("message_count", 0),
             "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None}
            for r in rows]


def get(user: str, tid: str) -> Optional[dict]:
    c = _coll()
    if c is None:
        return None
    t = c.find_one({"_id": tid, "user": user})
    if not t:
        return None
    return {"thread_id": t["_id"], "title": t.get("title") or "New chat",
            "messages": [{"role": m["role"], "content": m["content"],
                          **({"data": m["data"]} if m.get("data") else {})}
                         for m in (t.get("messages") or [])]}


def history(user: str, tid: str) -> List[dict]:
    """Prior messages (role/content only) for the agent, capped to MAX_HISTORY."""
    t = get(user, tid)
    if not t:
        return []
    return t["messages"][-MAX_HISTORY:]


def append(user: str, tid: str, role: str, content: str, data: Optional[dict] = None) -> None:
    c = _coll()
    if c is None:
        return
    msg: Dict[str, Any] = {"role": role, "content": content, "ts": _now()}
    if data:
        msg["data"] = data
    c.update_one({"_id": tid, "user": user},
                 {"$push": {"messages": msg}, "$set": {"updated_at": _now()}})


def rename(user: str, tid: str, title: str) -> None:
    c = _coll()
    if c is not None:
        c.update_one({"_id": tid, "user": user}, {"$set": {"title": (title or "Untitled")[:80]}})


def delete(user: str, tid: str) -> None:
    c = _coll()
    if c is not None:
        c.delete_one({"_id": tid, "user": user})
