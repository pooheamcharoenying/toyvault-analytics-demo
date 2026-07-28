"""Signed session tokens — a minimal HMAC-SHA256 token (like a stripped-down JWT),
no external dependency. Payload is base64url JSON; the signature is
HMAC-SHA256(payload, SESSION_SECRET). Tampering or expiry -> verify() returns None.

The token carries only identity (username, role, display name) and an expiry — no
secrets. The secret never leaves the server.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from app.core.config import get_settings


def _secret() -> bytes:
    s = get_settings()
    # Prefer an explicit SESSION_SECRET; fall back to a stable per-deployment value
    # (the bcrypt admin hash) so dev works without extra config. Set SESSION_SECRET
    # in production.
    raw = s.SESSION_SECRET or s.BASIC_AUTH_PASSWORD_HASH or "toyvault-dev-secret"
    return raw.encode("utf-8")


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(body: str) -> str:
    return _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())


def issue(username: str, role: str, display_name: str, ttl_hours: Optional[int] = None) -> str:
    s = get_settings()
    ttl = (ttl_hours or s.SESSION_TTL_HOURS) * 3600
    payload = {"sub": username, "role": role, "name": display_name,
               "exp": int(time.time()) + ttl}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body)}"


def verify(token: str) -> Optional[dict]:
    """Return the payload dict if the token is valid and unexpired, else None."""
    if not token or "." not in token:
        return None
    try:
        body, sig = token.split(".", 1)
        if not hmac.compare_digest(sig, _sign(body)):
            return None
        payload = json.loads(_unb64(body))
    except Exception:
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    return payload
