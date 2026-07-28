"""Minimal MongoDB connection layer for ToyVault.

The analytics DATA still comes from the Excel workbook (Spaces / EXCEL_SOURCE_URL);
Mongo here only backs the app-owned collections added by the overhaul — `users`
(per-user login), and later the planogram / assistant-threads / LINE-binding
collections. It is NOT the analytics data source.

Nothing runs unless a connection is configured (either MONGODB_URI, or
MONGODB_USER_ME + MONGODB_PASSWORD_ME + MONGODB_HOST). Unset => Mongo-backed
features report "not configured" and the rest of the app is unaffected.

Everything is scoped to a single database (MONGODB_DB, default "toyvaultdemo").
This module never drops a database or reaches outside MONGODB_DB — the Atlas
cluster is shared with other apps, so isolation is by database name.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

_client = None


def _setting(name: str) -> Optional[str]:
    """Real env var first (Railway), then pydantic Settings / .env (local dev).
    Lazy + defensive so importing this module never forces a settings import."""
    val = os.environ.get(name)
    if val:
        return val
    try:
        from app.core.config import get_settings
        return getattr(get_settings(), name, None) or None
    except Exception:
        return None


def get_uri() -> Optional[str]:
    """Resolve the connection URI, in priority order:

    1. ``MONGODB_URI`` — a full connection string (how Railway supplies it).
    2. ``MONGODB_USER_ME`` + ``MONGODB_PASSWORD_ME`` + ``MONGODB_HOST`` — assembled
       here for local dev. The password is URL-encoded automatically.

    NEVER log the return value — it contains the password.
    """
    uri = _setting("MONGODB_URI")
    if uri:
        return uri
    user = _setting("MONGODB_USER_ME")
    password = _setting("MONGODB_PASSWORD_ME")
    host = _setting("MONGODB_HOST")
    if user and password and host:
        from urllib.parse import quote_plus
        return (
            f"mongodb+srv://{quote_plus(user)}:{quote_plus(password)}@{host}"
            f"/?retryWrites=true&w=majority&appName=toyvaultdemo"
        )
    return None


def describe_credential_source() -> str:
    """Which config path supplied the URI. Safe to log — names only, no values."""
    if _setting("MONGODB_URI"):
        return "MONGODB_URI (full connection string)"
    if _setting("MONGODB_USER_ME") and _setting("MONGODB_PASSWORD_ME") and _setting("MONGODB_HOST"):
        return "MONGODB_USER_ME + MONGODB_PASSWORD_ME + MONGODB_HOST (assembled)"
    return "none — Mongo not configured"


def get_db_name() -> str:
    """The database this app owns (scoped; never drops or reaches outside it)."""
    return _setting("MONGODB_DB") or "toyvaultdemo"


def is_enabled() -> bool:
    return bool(get_uri())


def get_db():
    """Return a pymongo Database, or None if unconfigured / driver missing.
    Never raises — callers degrade gracefully when Mongo is absent."""
    global _client
    uri = get_uri()
    if not uri:
        return None
    if _client is None:
        try:
            from pymongo import MongoClient
        except ImportError:
            logger.error("MONGODB_URI is set but pymongo is not installed")
            return None
        _client = MongoClient(uri, serverSelectionTimeoutMS=10_000)
    return _client[get_db_name()]
